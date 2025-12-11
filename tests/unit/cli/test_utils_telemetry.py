"""
Unit tests for the CLI Telemetry Middleware.
"""

import click
import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from jnkn.cli.utils_telemetry import TelemetryGroup

class TestTelemetryGroup:
    """Test the TelemetryGroup middleware."""

    @pytest.fixture
    def mock_service(self):
        """Fixture to mock the global telemetry service used by CLI."""
        with patch("jnkn.cli.utils_telemetry._service") as mock:
            yield mock

    def test_successful_command_tracking(self, mock_service):
        """Test that a successful command triggers a success event."""
        
        @click.group(cls=TelemetryGroup)
        def cli(): pass

        @cli.command()
        def hello(): click.echo("Hello")

        runner = CliRunner()
        result = runner.invoke(cli, ["hello"])

        assert result.exit_code == 0
        assert mock_service.track.called
        
        call_args = mock_service.track.call_args
        # track(event_name="...", properties={...})
        kwargs = call_args.kwargs
        assert kwargs["event_name"] == "command_run"
        
        props = kwargs["properties"]
        assert props["command"] == "hello"
        assert props["success"] is True
        assert props["exit_code"] == 0

    def test_explicit_exit_code_tracking(self, mock_service):
        """
        Test that ctx.exit(10) is captured correctly.
        """
        
        @click.group(cls=TelemetryGroup)
        def cli(): pass

        @cli.command(name="exit_cmd")
        @click.pass_context
        def exit_cmd(ctx):
            ctx.exit(10)

        runner = CliRunner()
        result = runner.invoke(cli, ["exit_cmd"])

        # ClickRunner catches SystemExit(10) and sets exit_code=10
        assert result.exit_code == 10
        
        assert mock_service.track.called
        kwargs = mock_service.track.call_args.kwargs
        props = kwargs["properties"]
        
        assert props["command"] == "exit_cmd"
        # Success is False because exit code != 0
        assert props["success"] is False
        assert props["exit_code"] != 0
