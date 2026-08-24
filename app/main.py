import asyncio
import json
import os
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from langsmith import traceable
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from app.agent import ProductionAgent
from app.cache import ResponseCache
from app.config import get_settings
from app.models import (
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthCheckResponse,
    MetricsResponse,
)
from app.monitoring import MetricsCollector, RequestTimer, get_logger
from app.security import SecurityPipeline

load_dotenv()

# Global component references (initialized in lifespan)
security: SecurityPipeline = None
cache: ResponseCache = None
metrics: MetricsCollector = None
agent: ProductionAgent = None
logger = get_logger()


# ==============================================================================
# Lifespan (Startup/Shutdown)
# ==============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Initialize all components on startup, clean up on shutdown.
    Modern FastAPI lifespan handler.
    """
    global security, cache, metrics, agent

    settings = get_settings()

    logger.info(
        "Starting production API...",
        extra={
            "extra_data": {
                "environment": settings.app_env,
                "primary_model": settings.primary_model,
                "tracing_enabled": settings.langchain_tracing_v2,
            }
        },
    )

    # Initialize components
    security = SecurityPipeline()
    cache = ResponseCache(ttl_seconds=settings.cache_ttl_seconds)
    metrics = MetricsCollector()
    agent = ProductionAgent()

    logger.info("All components initialized. Ready to serve requests.")

    yield  # App is running...

    # Shutdown
    logger.info("Shutting down...", extra={"extra_data": metrics.get_summary()})


# ==============================================================================
# Rate Limiter & App Setup
# ==============================================================================

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="DWD AI",
    description="A production-ready chat API with security, caching, rate limiting, and observability.",
    version="1.0.0",
    docs_url="/docs" if not get_settings().is_production else None,
    redoc_url="/redoc" if not get_settings().is_production else None,
    openapi_url="/openapi.json" if not get_settings().is_production else None,
    lifespan=lifespan,
)
app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# ==============================================================================
# Exception Handlers
# ==============================================================================

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": "Too many requests. Please slow down.",
        },
    )


# ==============================================================================
# Endpoints
# ==============================================================================

@app.get("/", tags=["System"])
async def root():
    """Serve the chat interface."""
    return FileResponse("frontend/index.html")


@app.get("/health", response_model=HealthCheckResponse, tags=["Monitoring"])
async def health_check():
    """
    Health check endpoint for Docker, orchestrators, and monitoring systems.
    """
    settings = get_settings()
    is_healthy = all([
        security is not None,
        cache is not None,
        metrics is not None,
        agent is not None,
    ])
    return HealthCheckResponse(
        status="healthy" if is_healthy else "degraded",
        environment=settings.app_env,
        version="1.0.0",
        checks={
            "security": "ok" if security else "uninitialized",
            "cache": "ok" if cache else "uninitialized",
            "metrics": "ok" if metrics else "uninitialized",
            "agent": "ok" if agent else "uninitialized",
        },
    )


@app.get("/metrics", response_model=MetricsResponse, tags=["Monitoring"])
async def get_metrics():
    """
    Metrics endpoint exposing application usage, latency, and cache statistics.
    """
    if get_settings().is_production:
        raise HTTPException(status_code=404, detail="Not found")
    if metrics is None:
        return MetricsResponse()
    return MetricsResponse(**metrics.get_metrics_data())

@app.get("/cache/stats")
async def cache_stats():
    """Cache performance statistics."""
    if get_settings().is_production:
        raise HTTPException(status_code=404, detail="Not found")
    return cache.stats

@app.post("/chat", response_model=ChatResponse, tags=["Chat"])
@limiter.limit(f"{get_settings().ratelimit_per_minute}/minute")
@traceable(name="chat_endpoint")
async def chat(request: Request, body: ChatRequest):
    """
    Main chat endpoint.

    Flow:
    1. Security checkpoint (Injection check + PII masking)
    2. Cache lookup (returns cached response if hit)
    3. LangGraph agent invocation (if cache miss)
    4. Output validation & PII check
    5. Store validated response in cache
    6. Record metrics and return response
    """
    with RequestTimer() as timer:
        security_notes = []

        # Step 1: Security Check
        is_allowed, cleaned_message, notes = security.check_input(body.message)
        security_notes.extend(notes)

        history_payload = [item.model_dump() for item in body.history]
        cache_query = json.dumps(
            {"message": cleaned_message, "history": history_payload},
            sort_keys=True,
        )

        if not is_allowed:
            logger.warning(
                "Request blocked by security",
                extra={
                    "extra_data": {
                        "reason": notes,
                        "thread_id": body.thread_id,
                    }
                },
            )
            metrics.record_request(latency_ms=0, error=True)
            raise HTTPException(
                status_code=400,
                detail="Your message was blocked by our security filters.",
            )

        # Step 2: Cache Lookup
        cached_response = cache.get(cache_query)
        if cached_response is not None:
            metrics.record_request(latency_ms=0, cache_hit=True)
            logger.info(
                "Cache hit",
                extra={"extra_data": {"thread_id": body.thread_id}},
            )
            return ChatResponse(
                response=cached_response,
                thread_id=body.thread_id,
                model_used="cache",
                cached=True,
                security_notes=security_notes,
                processing_time_ms=0.0,
            )

        # Step 3: Agent Invocation (run in threadpool to prevent blocking the event loop)
        try:
            result = await asyncio.to_thread(
                agent.invoke,
                cleaned_message,
                history_payload,
            )
        except Exception as e:
            logger.error(
                f"Agent invocation failed: {e}",
                extra={
                    "extra_data": {
                        "thread_id": body.thread_id,
                        "error": str(e),
                    }
                },
            )
            metrics.record_request(latency_ms=0, error=True)
            raise HTTPException(
                status_code=500,
                detail="An error occurred while processing your request.",
            )

        response_text = result["response"]
        model_used = result["model_used"]

        # Step 4: Output Validation
        validated_response, output_warnings = security.check_output(response_text)
        security_notes.extend(output_warnings)

        # Step 5: Cache Storage
        cache.set(cache_query, validated_response)

        # Step 6: Metrics & Response Return
        input_tokens = int(len(cleaned_message.split()) * 1.3)
        output_tokens = int(len(validated_response.split()) * 1.3)

        metrics.record_request(
            latency_ms=timer.elapsed_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit=False,
        )

        if security_notes:
            logger.info(
                "Security notes",
                extra={
                    "extra_data": {
                        "notes": security_notes,
                        "thread_id": body.thread_id,
                    }
                },
            )

        logger.info(
            "Request completed",
            extra={
                "extra_data": {
                    "thread_id": body.thread_id,
                    "model_used": model_used,
                    "latency_ms": round(timer.elapsed_ms),
                }
            },
        )

        return ChatResponse(
            response=validated_response,
            thread_id=body.thread_id,
            model_used=model_used,
            cached=False,
            security_notes=security_notes,
            processing_time_ms=round(timer.elapsed_ms, 2),
        )