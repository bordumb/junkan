"""
Standardized Error Definitions.

Defines the error codes and structure for API error responses.
"""

from enum import Enum
from typing import Any, Dict

from pydantic import BaseModel


class ErrorCode(str, Enum):
    """
    Standard error codes for machine-readable error handling.
    """

    # General System Errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"

    # Input/Config Errors
    INVALID_INPUT = "INVALID_INPUT"
    CONFIG_MISSING = "CONFIG_MISSING"
    CONFIG_INVALID = "CONFIG_INVALID"

    # Graph/State Errors
    GRAPH_MISSING = "GRAPH_MISSING"
    GRAPH_EMPTY = "GRAPH_EMPTY"
    NODE_MISSING = "NODE_MISSING"

    # Parsing Errors
    PARSER_FAILED = "PARSER_FAILED"
    FILE_READ_ERROR = "FILE_READ_ERROR"

    # Analysis Errors
    BLAST_RADIUS_FAILED = "BLAST_RADIUS_FAILED"
    CHECK_FAILED = "CHECK_FAILED"


class StructuredError(BaseModel):
    """
    A structured error object for machine consumption.
    """

    code: ErrorCode
    message: str
    details: Dict[str, Any] = {}
    suggestion: str | None = None
