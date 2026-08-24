"""
API Requests and Responses Models for the application.
Pydantic models for input validation and output formatting of API requests and responses.
"""

from uuid import uuid4
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

class ChatRequest(BaseModel):
    """
    Model for chat request payload. 
    incoming chat request.
    """
    message: str = Field(
        ..., 
        min_length=2, 
        max_length=1000, 
        description="The message content sent by the user.",
        examples=["What is Retrieval-Augmented Generation (RAG)?"]
    )
    thread_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Conversation thread ID, Unique identifier for the chat thread.",
        examples=["user-session-12345"]
    )
    history: list["ConversationMessage"] = Field(
        default_factory=list,
        max_length=12,
        description="Recent conversation messages used for context."
    )

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must contain non-whitespace characters")
        return value

    model_config = {
        "json_schema_extra": {
            "example": {
                "message": "What is Retrieval-Augmented Generation (RAG)?",
                "thread_id": "thread-12345"
            }
        }
    }


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=4000)
    
class ChatResponse(BaseModel):
    """
    Model for chat response payload.
    outgoing chat response.
    """
    response: str = Field(
        ..., 
        description="The message content sent by the system in response to the user."
        )
    thread_id: str = Field(
        ..., 
        description="Conversation thread ID, Unique identifier for the chat thread."
        )
    model_used: str = Field(
        ...,
        description="The language model used to generate the response."
    )
    cached: bool = Field(
        default=False,
    )
    security_notes: list[str] = Field(
        default_factory=list,
        description="Security checks applied to the request or response.",
    )
    processing_time_ms: float = Field(
        default=0.0,
        description="Time taken to process the request in milliseconds."
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), 
        description="Timestamp of when the response was generated."
        )
    
class HealthCheckResponse(BaseModel):
    """
    Model for health check response payload.
    """
    status: str = Field(
        default="healthy", 
        description="The current health status of the application."
        )
    environment: str = Field(
        default="development", 
        description="The current environment the application is running in (e.g., development, production)."
        )
    version: str = Field(
        default="1.0.0",
        description="The current version of the application."
    )
    checks: dict = Field(
        default_factory=dict,
        description="Detailed health checks for various components of the application."
    )

class MetricsResponse(BaseModel):

    """
    Model for metrics response payload.
    """
    total_requests: int = Field(
        default=0,
        description="Total number of requests received by the application."
    )
    total_errors: int = Field(
        default=0,
        description="Total number of errors encountered by the application."
    )
    error_rate: float = Field(
        default=0.0,
        description="Error rate calculated as the ratio of total errors to total requests."
    )
    avg_latency_ms: float = Field(
        default=0.0,
        description="Average latency of requests in milliseconds."
    )
    cache_hit_rate: str = Field(
        default="0.00%",
        description="Cache hit rate formatted as a percentage."
    )
    successful_requests: int = Field(
        default=0,
        description="Total number of successful requests processed by the application."
    )
    total_input_tokens: int = Field(
        default=0,
        description="Total number of input tokens processed by the application."
    )
    total_output_tokens: int = Field(
        default=0,
        description="Total number of output tokens processed by the application."
    )

class ErrorResponse(BaseModel):
    """
    Model for error response payload.
    Standard error response structure for API endpoints, providing error details and context.
    """
    error: str = Field(
        ..., 
        description="A brief error code or identifier for the error."
        )
    detail: str = Field(
        ...,
        description="Additional details about the error."
    )
    request_id: str = Field(
        ..., 
        description="Unique identifier for the request that caused the error."
        )