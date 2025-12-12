"""
Standard API Envelope Definition.

This file defines the immutable contract for all CLI JSON outputs.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Generic, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from jnkn import __version__

from .errors import StructuredError

# Generic type for the 'data' payload
T = TypeVar("T")


class Status(str, Enum):
    SUCCESS = "success"
    ERROR = "error"
    PARTIAL = "partial"


class Meta(BaseModel):
    """Metadata about the request/execution context."""

    spec_version: str = "1.0"
    cli_version: str = Field(default_factory=lambda: __version__)
    command: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    duration_ms: float = 0.0
    request_id: str = Field(default_factory=lambda: str(uuid4()))


class StandardResponse(BaseModel, Generic[T]):
    """
    The Standard Envelope for all JSON outputs.

    Attributes:
        meta: Execution metadata (timing, versions).
        status: High-level outcome.
        data: The strictly typed domain payload (Generic).
        error: Structured error details if status is 'error' or 'partial'.
    """

    meta: Meta
    status: Status
    data: T | None = None
    error: StructuredError | None = None

    model_config = {"json_encoders": {datetime: lambda v: v.isoformat()}}
