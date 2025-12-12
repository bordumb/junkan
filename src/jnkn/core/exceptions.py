"""
Typed Exception Hierarchy.

Maps internal Python exceptions to standard API ErrorCodes.
"""

from typing import Any, Dict

from .api.errors import ErrorCode


class JnknError(Exception):
    """Base class for all Jnkn exceptions."""

    def __init__(
        self,
        message: str,
        code: ErrorCode = ErrorCode.INTERNAL_ERROR,
        details: Dict[str, Any] | None = None,
        suggestion: str | None = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.suggestion = suggestion


class GraphNotFoundError(JnknError):
    def __init__(self, path: str):
        super().__init__(
            f"Graph database not found at {path}",
            code=ErrorCode.GRAPH_MISSING,
            details={"path": path},
            suggestion="Run 'jnkn scan' to generate the graph first.",
        )


class NodeNotFoundError(JnknError):
    def __init__(self, node_id: str):
        super().__init__(
            f"Artifact not found: {node_id}",
            code=ErrorCode.NODE_MISSING,
            details={"node_id": node_id},
            suggestion="Check the spelling or run 'jnkn scan' to update the graph.",
        )


class ConfigError(JnknError):
    def __init__(self, message: str, details: Dict | None = None):
        super().__init__(
            message,
            code=ErrorCode.CONFIG_INVALID,
            details=details,
            suggestion="Run 'jnkn init' to recreate a valid configuration.",
        )
