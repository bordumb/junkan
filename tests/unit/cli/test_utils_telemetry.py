"""
Unit tests for the CLI Telemetry Middleware.
"""

import click
import pytest
from unittest.mock import patch
from click.testing import CliRunner

from jnkn.cli.utils_telemetry import TelemetryGroup

class TestTelemetryGroup:
    """Test the TelemetryGroup middleware."""

    @pytest.fixture
    def mock_track_event(self):
        """
        Fixture to mock the telemetry tracking function.
        Returns the mock object for assertion.
        """
        # Patch the specific import used in utils_telemetry.py
        with patch("jnkn.cli.utils_telemetry.track_event") as mock:
            yield mock

    def test_successful_command_tracking(self, mock_track_event):
        """Test that a successful command triggers a success event."""
        
        @click.group(cls=TelemetryGroup)
        def cli():
            pass

        @cli.command()
        def hello():
            click.echo("Hello")

        runner = CliRunner()
        result = runner.invoke(cli, ["hello"])

        assert result.exit_code == 0
        assert "Hello" in result.output
        
        assert mock_track_event.called
        
        # Verify telemetry payload
        call_kwargs = mock_track_event.call_args.kwargs
        event_name = call_kwargs.get("name")
        props = call_kwargs.get("properties")

        assert event_name == "command_run"
        assert props["command"] == "hello"
        assert props["success"] is True
        assert props["exit_code"] == 0
        assert props["error_type"] is None
        assert props["duration_ms"] >= 0

    def test_failed_command_tracking(self, mock_track_event):
        """Test that a failing command triggers a failure event."""
        
        @click.group(cls=TelemetryGroup)
        def cli():
            pass

        @cli.command()
        def fail():
            raise ValueError("Something went wrong")

        runner = CliRunner()
        result = runner.invoke(cli, ["fail"])

        assert result.exit_code != 0
        
        assert mock_track_event.called
        call_kwargs = mock_track_event.call_args.kwargs
        props = call_kwargs.get("properties")

        assert props["command"] == "fail"
        assert props["success"] is False
        assert props["exit_code"] == 1
        assert props["error_type"] == "ValueError"

    def test_explicit_exit_code_tracking(self, mock_track_event):
        """
        Test that ctx.exit(10) is captured correctly.
        
        This uses Click's native exit mechanism, which raises SystemExit(10).
        The middleware should capture the '10', mark success as False,
        and re-raise it so the runner sees it.
        """
        
        @click.group(cls=TelemetryGroup)
        def cli():
            pass

        @cli.command()
        @click.pass_context
        def exit_cmd(ctx):
            # ctx.exit() is the cleaner, framework-native way to exit
            ctx.exit(10)

        runner = CliRunner()
        result = runner.invoke(cli, ["exit_cmd"])

        # 1. Verify the CLI behaved as expected (exited with 10)
        assert result.exit_code == 10
        
        # 2. Verify telemetry captured the specific code
        assert mock_track_event.called
        call_kwargs = mock_track_event.call_args.kwargs
        props = call_kwargs.get("properties")

        assert props["command"] == "exit_cmd"
        assert props["exit_code"] == 10
        assert props["success"] is False
        # ctx.exit raises SystemExit internally
        assert props["error_type"] == "SystemExit"