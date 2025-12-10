"""
Comprehensive unit tests for the 'init' command.
Covers:
- Stack detection logic
- Gitignore creation/updating
- Standard initialization flow (interactive)
- Demo mode initialization (automated)
- Telemetry configuration
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml
from click.testing import CliRunner

from jnkn.cli.commands.initialize import create_gitignore, detect_stack, init


class TestStackDetection:
    """Unit tests for the detect_stack helper."""

    def test_detects_python(self, tmp_path):
        (tmp_path / "pyproject.toml").touch()
        assert "python" in detect_stack(tmp_path)

        # Cleanup and test .py file
        (tmp_path / "pyproject.toml").unlink()
        (tmp_path / "script.py").touch()
        assert "python" in detect_stack(tmp_path)

    def test_detects_terraform(self, tmp_path):
        (tmp_path / "main.tf").touch()
        assert "terraform" in detect_stack(tmp_path)

    def test_detects_kubernetes(self, tmp_path):
        (tmp_path / "deploy.yaml").touch()
        assert "kubernetes" in detect_stack(tmp_path)

    def test_detects_dbt(self, tmp_path):
        (tmp_path / "dbt_project.yml").touch()
        assert "dbt" in detect_stack(tmp_path)

    def test_detects_javascript(self, tmp_path):
        (tmp_path / "package.json").touch()
        assert "javascript" in detect_stack(tmp_path)

    def test_detects_nothing(self, tmp_path):
        assert detect_stack(tmp_path) == set()


class TestGitIgnore:
    """Unit tests for create_gitignore helper."""

    def test_creates_new_gitignore(self, tmp_path):
        jnkn_dir = tmp_path / ".jnkn"
        jnkn_dir.mkdir()
        
        create_gitignore(jnkn_dir)
        
        gitignore = tmp_path / ".gitignore"
        assert gitignore.exists()
        content = gitignore.read_text()
        assert ".jnkn/" in content
        assert "jnkn.db" in content

    def test_appends_to_existing_gitignore(self, tmp_path):
        gitignore = tmp_path / ".gitignore"
        gitignore.write_text("node_modules/\n")
        
        jnkn_dir = tmp_path / ".jnkn"
        jnkn_dir.mkdir()
        
        create_gitignore(jnkn_dir)
        
        content = gitignore.read_text()
        assert "node_modules/" in content
        assert ".jnkn/" in content

    def test_skips_if_already_present(self, tmp_path):
        gitignore = tmp_path / ".gitignore"
        initial_content = ".jnkn/\n"
        gitignore.write_text(initial_content)
        
        jnkn_dir = tmp_path / ".jnkn"
        jnkn_dir.mkdir()
        
        create_gitignore(jnkn_dir)
        
        # Should not duplicate
        assert gitignore.read_text() == initial_content


class TestInitCommand:
    """Integration tests for the standard init command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_aborts_if_config_exists_and_declined(self, mock_confirm, runner):
        """Test aborting when config exists and user says 'no'."""
        mock_confirm.return_value = False  # User says NO to overwrite

        with runner.isolated_filesystem():
            # Setup existing config INSIDE isolation
            jnkn_dir = Path(".jnkn")
            jnkn_dir.mkdir()
            (jnkn_dir / "config.yaml").touch()

            result = runner.invoke(init)

        assert result.exit_code == 0
        assert "Configuration already exists" in result.output
        assert "Aborted" in result.output

    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_overwrites_if_accepted(self, mock_confirm, runner):
        """Test overwriting when config exists and user says 'yes'."""
        # 1. Overwrite? YES
        # 2. Telemetry? YES
        mock_confirm.side_effect = [True, True]

        with runner.isolated_filesystem():
            # Setup existing config INSIDE isolation
            jnkn_dir = Path(".jnkn")
            jnkn_dir.mkdir()
            config_file = jnkn_dir / "config.yaml"
            config_file.write_text("old_content")

            result = runner.invoke(init)

            assert result.exit_code == 0
            assert "Initialized successfully" in result.output
            
            # Verify content changed
            with open(config_file) as f:
                data = yaml.safe_load(f)
            assert data.get("version") == "1.0"  # It's the new config

    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_force_flag_skips_prompt(self, mock_confirm, runner):
        """Test --force skips the overwrite prompt."""
        # Only prompt should be for telemetry
        mock_confirm.side_effect = [True]

        with runner.isolated_filesystem():
            # Setup existing config INSIDE isolation
            jnkn_dir = Path(".jnkn")
            jnkn_dir.mkdir()
            (jnkn_dir / "config.yaml").touch()

            result = runner.invoke(init, ["--force"])

        assert result.exit_code == 0
        assert "Initialized successfully" in result.output

    @patch("jnkn.cli.commands.initialize.detect_stack")
    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_generates_correct_includes(self, mock_confirm, mock_detect, runner):
        """Test that detected stack results in correct include patterns."""
        mock_detect.return_value = {"python", "terraform"}
        mock_confirm.return_value = True  # Accept telemetry

        with runner.isolated_filesystem():
            runner.invoke(init)
            
            config_path = Path(".jnkn/config.yaml")
            with open(config_path) as f:
                config = yaml.safe_load(f)
                
            includes = config["scan"]["include"]
            assert "**/*.py" in includes
            assert "**/*.tf" in includes
            assert "**/*.js" not in includes

    @patch("jnkn.cli.commands.initialize.detect_stack")
    @patch("jnkn.cli.commands.initialize.Confirm.ask")
    def test_init_fallback_includes(self, mock_confirm, mock_detect, runner):
        """Test fallback to **/* if no stack detected."""
        mock_detect.return_value = set()
        mock_confirm.return_value = True

        with runner.isolated_filesystem():
            result = runner.invoke(init)
            
            assert "No specific technologies detected" in result.output
            
            config_path = Path(".jnkn/config.yaml")
            with open(config_path) as f:
                config = yaml.safe_load(f)
                
            assert config["scan"]["include"] == ["**/*"]


class TestInitDemo:
    """Integration tests for the 'init --demo' command flow."""

    @patch("jnkn.cli.commands.initialize.DemoManager")
    def test_init_demo_flow(self, MockDemoManager, tmp_path):
        """Verify --demo workflow: provisions, skips prompts, configures defaults."""
        runner = CliRunner()
        
        # Setup mocks
        mock_manager = MockDemoManager.return_value
        demo_path = tmp_path / "jnkn-demo"
        demo_path.mkdir()
        mock_manager.provision.return_value = demo_path

        # We need to run inside the tmp_path so the command sees the CWD correctly
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init, ["--demo"])

            assert result.exit_code == 0
            assert "Provisioning demo environment" in result.output
            assert "Ready to go!" in result.output

            # Verify provision called
            mock_manager.provision.assert_called_once()

            # Verify .jnkn config was created INSIDE the demo dir
            # Note: The command logic calls _init_project(demo_dir, ...)
            config_path = demo_path / ".jnkn/config.yaml"
            assert config_path.exists()

            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            # Verify demo defaults
            assert config["telemetry"]["enabled"] is True
            # Demo stack is hardcoded to python, terraform, k8s
            includes = config["scan"]["include"]
            assert "**/*.py" in includes
            assert "**/*.tf" in includes
            assert "**/*.yaml" in includes