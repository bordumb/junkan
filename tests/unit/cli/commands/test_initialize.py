"""
Unit tests for the 'init' command with telemetry.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from jnkn.cli.commands.initialize import init


class TestInitCommand:
    """Test the init command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_cwd(self, tmp_path):
        """Mock current working directory to a temp path."""
        with patch("pathlib.Path.cwd", return_value=tmp_path):
            yield tmp_path

    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_creates_config_with_telemetry_enabled(self, mock_confirm, runner, mock_cwd):
        """Test that accepting telemetry writes enabled=True to config."""
        # 1. Overwrite? (No, file doesn't exist)
        # 2. Allow telemetry? (Yes)
        mock_confirm.side_effect = [True]  

        result = runner.invoke(init)
        
        assert result.exit_code == 0
        assert "Initialized successfully" in result.output

        config_path = mock_cwd / ".jnkn/config.yaml"
        assert config_path.exists()

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config["telemetry"]["enabled"] is True
        assert "distinct_id" in config["telemetry"]
        assert len(config["telemetry"]["distinct_id"]) > 0

    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_creates_config_with_telemetry_disabled(self, mock_confirm, runner, mock_cwd):
        """Test that declining telemetry writes enabled=False to config."""
        # Mock Confirm.ask to return False (user says 'n')
        mock_confirm.return_value = False

        result = runner.invoke(init)
        
        assert result.exit_code == 0
        
        config_path = mock_cwd / ".jnkn/config.yaml"
        assert config_path.exists()

        with open(config_path) as f:
            config = yaml.safe_load(f)

        assert config["telemetry"]["enabled"] is False
        # Distinct ID should still be generated for consistency, just not used
        assert "distinct_id" in config["telemetry"]

    @patch("jnkn.cli.commands.initialize.detect_stack")
    def test_init_stack_detection(self, mock_detect, runner, mock_cwd):
        """Test that stack detection influences the config."""
        mock_detect.return_value = {"python", "terraform"}
        
        # Auto-accept telemetry
        with patch("jnkn.cli.commands.initialize.Confirm.ask", return_value=True):
            runner.invoke(init)

        config_path = mock_cwd / ".jnkn/config.yaml"
        with open(config_path) as f:
            config = yaml.safe_load(f)

        includes = config["scan"]["include"]
        assert "**/*.py" in includes
        assert "**/*.tf" in includes
        assert "**/*.js" not in includes