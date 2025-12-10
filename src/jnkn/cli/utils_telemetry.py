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
        # Determine the subcommand being run
        # Use getattr to handle potential deprecations or missing attributes safely
        cmd_args = getattr(ctx, "protected_args", []) or getattr(ctx, "args", [])
        command_name = cmd_args[0] if cmd_args else "unknown"
        subcommand = ctx.invoked_subcommand or command_name
        
        start_time = time.perf_counter()
        exit_code = 0
        error_type = None

        try:
            return super().invoke(ctx)
        except Exception as e:
            # Handle standard exceptions (crashes)
            exit_code = 1
            error_type = type(e).__name__
            raise
        except SystemExit as e:
            # Handle intentional exits via sys.exit() or ctx.exit()
            # Click's ctx.exit(N) raises SystemExit(N)
            exit_code = e.code if isinstance(e.code, int) else 1
            if exit_code != 0:
                error_type = "SystemExit"
            raise
        finally:
            # CRITICAL: Wrap telemetry in try/except so it NEVER affects the CLI exit code
            # If this block raises an exception, it would mask original errors.
            try:
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
