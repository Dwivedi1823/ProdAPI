"""
Monitoring & Structured Logging.
Production-Grade metrics collection and JSON logging.
"""

import logging
import json
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Callable
from langchain_openai import ChatOpenAI
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import HumanMessage
from langsmith import traceable
from dotenv import load_dotenv

load_dotenv()



class JSONFormatter(logging.Formatter):

    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName
        }

        # Merge any extra data attached to the record
        if hasattr(record, "extra_data"):
            log_obj.update(record.extra_data)
        return json.dumps(log_obj)

# def setup_logging():
#     """Setup structured JSON logging."""

#     logger = logging.getLogger("langgraph_app")
#     logger.setLevel(logging.INFO)

#     handler = logging.StreamHandler()
#     handler.setFormatter(JSONFormatter())
#     logger.addHandler(handler)

#     return logger

def get_logger(name:  str = "production-api") -> logging.Logger:
    """Create a structured JSON logger"""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)

    return logger





class MetricsCollector:
    """
    Collects and aggreagates application metrics.

    In prod, replace with Promethus client:
        from prometheus)client import Counter, Histogram
    """

    def __init__(self):
        self.metrics = {
            "requests_total": 0,
            "errors_total": 0,
            "latency_sum": 0,
            "latency_count": 0,
            "tokens_input": 0,
            "tokens_output": 0,
            "cache_hits": 0,
            "cache_misses": 0,
        }

    def record_request(
            self,
            latency_ms: float,
            input_tokens: int = 0,
            output_tokens: int = 0,
            error: bool = False,
            cache_hit: bool = False
    ):
        self.metrics["requests_total"] += 1
        self.metrics["latency_sum"] += latency_ms
        self.metrics["latency_count"] += 1
        self.metrics["tokens_input"] += input_tokens
        self.metrics["tokens_output"] += output_tokens

        if error:
            self.metrics["errors_total"] += 1

        if cache_hit:
            self.metrics["cache_hits"] += 1
        else:
            self.metrics["cache_misses"] += 1

    def get_summary(self) -> dict:
        avg_latency = (
            self.metrics["latency_sum"] / self.metrics["latency_count"]
            if self.metrics["latency_count"] > 0
            else 0
        )
        error_rate = (
            self.metrics["errors_total"] / self.metrics["requests_total"]
            if self.metrics["requests_total"] > 0
            else 0
        )
        cache_hit_rate = (
            self.metrics["cache_hits"]
            / (self.metrics["cache_hits"] + self.metrics["cache_misses"])
            if (self.metrics["cache_hits"] + self.metrics["cache_misses"]) > 0
            else 0
        )

        return {
            "total_requests": self.metrics["requests_total"],
            "total_errors": self.metrics["errors_total"],
            "error_rate": f"{error_rate:.2%}",
            "avg_latency_ms": round(avg_latency, 2),
            "total_input_tokens": self.metrics["tokens_input"],
            "total_output_tokens": self.metrics["tokens_output"],
            "cache_hit_rate": f"{cache_hit_rate:.2%}",
        }

    def get_metrics_data(self) -> dict:
        """Return raw metrics formatted for MetricsResponse model."""
        avg_latency = (
            self.metrics["latency_sum"] / self.metrics["latency_count"]
            if self.metrics["latency_count"] > 0
            else 0.0
        )
        error_rate = (
            self.metrics["errors_total"] / self.metrics["requests_total"]
            if self.metrics["requests_total"] > 0
            else 0.0
        )
        total_cache_lookups = self.metrics["cache_hits"] + self.metrics["cache_misses"]
        cache_hit_rate = (
            self.metrics["cache_hits"] / total_cache_lookups
            if total_cache_lookups > 0
            else 0.0
        )
        successful_requests = max(0, self.metrics["requests_total"] - self.metrics["errors_total"])

        return {
            "total_requests": self.metrics["requests_total"],
            "total_errors": self.metrics["errors_total"],
            "error_rate": round(error_rate, 4),
            "avg_latency_ms": round(avg_latency, 2),
            "cache_hit_rate": f"{cache_hit_rate:.2%}",
            "successful_requests": successful_requests,
            "total_input_tokens": self.metrics["tokens_input"],
            "total_output_tokens": self.metrics["tokens_output"],
        }

class RequestTimer:
    """Context manager for timing requests."""

    def __init__(self):
        self.start = 0.0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self.start) * 1000
# === Instrumented LLM ===


# class InstrumentedLLM:
#     """LLM with full instrumentation."""

#     def __init__(self):
#         self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
#         self.metrics = MetricsCollector()
#         self.logger = setup_logging()

#     @traceable(name="instrumented_invoke")
#     def invoke(self, query: str) -> str:
#         start_time = time.time()
#         error = False

#         try:
#             response = self.llm.invoke(query)
#             result = response.content

#             # Estimate tokens
#             input_tokens = len(query.split()) * 4 // 3
#             output_tokens = len(result.split()) * 4 // 3

#             self.metrics.record_request(
#                 latency_ms=(time.time() - start_time) * 1000,
#                 input_tokens=input_tokens,
#                 output_tokens=output_tokens,
#                 error=False,
#                 cache_hit=False,
#             )

#             self.logger.info(
#                 "LLM request completed",
#                 extra={
#                     "extra_data": {
#                         "latency_ms": (time.time() - start_time) * 1000,
#                         "input_tokens": input_tokens,
#                         "output_tokens": output_tokens,
#                     }
#                 },
#             )

#             return result

#         except Exception as e:
#             error = True
#             self.metrics.record_request(
#                 latency_ms=(time.time() - start_time) * 1000,
#                 input_tokens=0,
#                 output_tokens=0,
#                 error=True,
#                 cache_hit=False,
#             )

#             self.logger.error(
#                 f"LLM request failed: {e}", extra={"extra_data": {"error": str(e)}}
#             )

#             raise