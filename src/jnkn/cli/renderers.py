"""
JSON Renderer and Output Manager.

Responsible for:
1. Constructing the StandardResponse envelope.
2. Capturing stdout/stderr to prevent pollution of JSON output.
3. Ensuring strictly typed output.
"""

import contextlib
import io
import sys
import time
from typing import TypeVar

from pydantic import BaseModel

from ..core.api.envelope import Meta, StandardResponse, Status
from ..core.api.errors import ErrorCode, StructuredError
from ..core.exceptions import JnknError

T = TypeVar("T")


class JsonRenderer:
    def __init__(self, command_name: str):
        self.command_name = command_name
        self.start_time = time.perf_counter()
        self._stdout_capture = io.StringIO()
        self._stderr_capture = io.StringIO()

    @contextlib.contextmanager
    def capture(self):
        """
        Context manager to capture stdout/stderr.
        Essential for --json mode to prevent logging/print pollution.
        """
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        try:
            sys.stdout = self._stdout_capture
            sys.stderr = self._stderr_capture
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    def _get_duration(self) -> float:
        return round((time.perf_counter() - self.start_time) * 1000, 2)

    def render_success(self, data: BaseModel, print_output: bool = True):
        """Render a successful response."""
        response = StandardResponse(
            meta=Meta(
                command=self.command_name,
                duration_ms=self._get_duration()
            ),
            status=Status.SUCCESS,
            data=data
        )
        output = response.model_dump_json(indent=2)
        if print_output:
            print(output)
        return output

    def render_error(self, error: Exception, print_output: bool = True):
        """Render an error response from an Exception."""
        
        # Determine error code and details
        if isinstance(error, JnknError):
            code = error.code
            message = error.message
            details = error.details
            suggestion = error.suggestion
        else:
            code = ErrorCode.INTERNAL_ERROR
            message = str(error)
            details = {"type": type(error).__name__}
            suggestion = "Please report this issue on GitHub."

        # Include captured stderr in details for debugging
        captured_stderr = self._stderr_capture.getvalue()
        if captured_stderr:
            details["stderr_log"] = captured_stderr.strip()

        structured_error = StructuredError(
            code=code,
            message=message,
            details=details,
            suggestion=suggestion
        )

        response = StandardResponse(
            meta=Meta(
                command=self.command_name,
                duration_ms=self._get_duration()
            ),
            status=Status.ERROR,
            data=None,
            error=structured_error
        )
        
        output = response.model_dump_json(indent=2)
        if print_output:
            print(output)
        return output
