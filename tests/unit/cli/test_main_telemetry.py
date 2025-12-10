"""
Unit test to verify the main CLI entry point uses the TelemetryGroup.
"""

from jnkn.cli.main import main
from jnkn.cli.utils_telemetry import TelemetryGroup

def test_main_uses_telemetry_group():
    """Verify that the main click group is an instance of TelemetryGroup."""
    assert isinstance(main, TelemetryGroup)