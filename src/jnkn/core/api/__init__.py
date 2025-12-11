"""
Core API definitions for Jnkn JSON Output Standardization.
"""

from .envelope import Meta, StandardResponse, Status
from .errors import ErrorCode, StructuredError

__all__ = [
    "StandardResponse",
    "Meta",
    "Status",
    "StructuredError",
    "ErrorCode",
]
