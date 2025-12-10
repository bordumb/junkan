import time
from typing import Any

import click

from ..core.telemetry import track_event


class TelemetryGroup(click.Group):
    """
    A custom Click Group that wraps command invocation with telemetry tracking.

    This class acts as middleware, intercepting the `invoke` method to:
    1. Measure command duration.
    2. Capture success/failure states and exit codes.
    3. Ensure telemetry is sent even if the command crashes or exits early.
    """

    def invoke(self, ctx: click.Context) -> Any:
        """
        Intercept command invocation to track usage statistics.

        Args:
            ctx: The Click execution context.

        Returns:
            The result of the invoked command.
        """
        start_time = time.perf_counter()
        exit_code = 0
        error_type = None
        caught_exception = None

        try:
            return super().invoke(ctx)
        except SystemExit as e:
            # Handle intentional exits via sys.exit() or ctx.exit()
            exit_code = e.code if isinstance(e.code, int) else 1
            if exit_code != 0:
                error_type = "SystemExit"
            caught_exception = e
        except Exception as e:
            # Handle unexpected crashes
            exit_code = 1
            error_type = type(e).__name__
            caught_exception = e
        finally:
            # Telemetry logic runs in finally to ensure it sends even on crash
            try:
                # Resolve subcommand name. 
                # ctx.invoked_subcommand is populated by super().invoke()
                # If it's None (e.g. group called without command), use "main" or similar
                subcommand = ctx.invoked_subcommand or "unknown"
                
                # Fallback: if invoke failed before resolution, try to peek at args
                # (This mimics the previous logic but as a fallback only)
                if subcommand == "unknown":
                    # Access protected_args safely to avoid warnings if possible, 
                    # but it's the only reliable way to see what was passed if invoke crashed early.
                    # For now, we rely on the fact that if invoke crashed early, 
                    # it was likely an args error, so "unknown" is acceptable.
                    pass

                duration_ms = (time.perf_counter() - start_time) * 1000
                
                track_event(
                    name="command_run",
                    properties={
                        "command": subcommand,
                        "duration_ms": round(duration_ms, 2),
                        "success": exit_code == 0,
                        "exit_code": exit_code,
                        "error_type": error_type
                    }
                )
            except Exception:
                # Telemetry failures must be silent
                pass
        
        # Re-raise the exception to allow the CLI to handle it (print error, exit)
        if caught_exception:
            raise caught_exception
