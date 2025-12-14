"""
Unit tests for the 'check' CLI command.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from jnkn.cli.commands.check import check


class TestCheckCommand:
    
    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_engine(self):
        """
        Patches CheckEngine and sets up the return values correctly.
        Crucial: Sets .name and .value attributes explicitly to avoid MagicMock constructor pitfalls.
        """
        with patch("jnkn.cli.commands.check.CheckEngine") as mock:
            engine_instance = mock.return_value
            
            # Create a mock for the result Enum that behaves like the real one
            # We can't use MagicMock(name="PASS") because 'name' is a reserved constructor arg
            mock_result_enum = MagicMock()
            mock_result_enum.name = "PASS"
            mock_result_enum.value = 0
            
            # Setup the report object returned by analyze()
            report_mock = MagicMock()
            report_mock.result = mock_result_enum
            report_mock.changed_files = []
            report_mock.critical_count = 0
            report_mock.high_count = 0
            report_mock.violations = []
            
            engine_instance.analyze.return_value = report_mock
            yield mock

    @pytest.fixture
    def mock_git(self):
        with patch("jnkn.cli.commands.check.get_changed_files_from_git") as mock:
            mock.return_value = []
            yield mock

    def test_check_clean_run(self, runner, mock_engine, mock_git):
        """Test a run with no violations returns exit code 0."""
        # We must mock CheckEngine so we don't need a real DB
        result = runner.invoke(check, ["--git-diff", "main", "HEAD"])
        
        # If this fails with 1, check the mocked report attributes
        assert result.exit_code == 0, f"Command failed with output: {result.output}"
        assert "Analysis Complete" in result.output
        assert "Result: PASS" in result.output

    def test_check_critical_failure(self, runner, mock_engine, mock_git):
        """Test that critical violations trigger a failure exit code when flag is set."""
        # Update the mock for this specific test case
        engine_instance = mock_engine.return_value
        
        # We can't just set attributes on the return_value if it was already accessed?
        # Safe way: configure the specific report object
        report = engine_instance.analyze.return_value
        report.critical_count = 1
        
        # Create a violation mock that has the required attributes
        violation = MagicMock()
        violation.severity = "critical"
        violation.message = "Critical infra change"
        violation.rule = "INFRA_CHANGE"
        report.violations = [violation]
        
        # Invoke with failure flag
        result = runner.invoke(check, ["--git-diff", "main", "HEAD", "--fail-if-critical"])
        
        assert result.exit_code == 1
        assert "Result: BLOCKED" in result.output
        assert "Critical infra change" in result.output

    def test_check_json_output(self, runner, mock_engine, mock_git):
        """Test that --json flag produces valid JSON output."""
        result = runner.invoke(check, ["--git-diff", "main", "HEAD", "--json"])
        
        assert result.exit_code == 0
        try:
            data = json.loads(result.output)
        except json.JSONDecodeError:
            pytest.fail(f"Output is not valid JSON: {result.output}")
            
        assert data["status"] == "success"
        assert data["meta"]["command"] == "check"
        assert data["data"]["result"] == "PASS"

    def test_auto_scan_trigger(self, runner, mock_git):
        """
        Test that a missing graph triggers the auto-scan logic.
        
        NOTE: We do NOT request 'mock_engine' here because we want to test the REAL 
        CheckEngine logic that calls create_default_engine().
        """
        with patch("jnkn.cli.commands.check.load_graph", return_value=None), \
             patch("jnkn.cli.commands.check.create_default_engine") as mock_create_engine, \
             patch("jnkn.cli.commands.check.SQLiteStorage") as mock_storage, \
             patch("jnkn.cli.commands.check.Stitcher"):
             
             # Setup the scan result to be successful
             mock_engine_instance = mock_create_engine.return_value
             # We need to ensure scan_and_store returns a Result object (Ok)
             # Mocking the Result object interface
             ok_result = MagicMock()
             ok_result.is_err.return_value = False
             mock_engine_instance.scan_and_store.return_value = ok_result
             
             # We also need the subsequent load_graph to return a dummy graph
             # so analysis doesn't crash
             mock_storage_instance = mock_storage.return_value
             mock_graph = MagicMock()
             mock_graph.node_count = 10
             # load_graph is called on storage instance
             mock_storage_instance.load_graph.return_value = mock_graph
             
             # Also need to patch BlastRadiusAnalyzer since we don't have a real graph
             with patch("jnkn.cli.commands.check.BlastRadiusAnalyzer") as mock_analyzer:
                 mock_analyzer.return_value.calculate.return_value = {"count": 0}
                 
                 result = runner.invoke(check, ["--git-diff", "main", "HEAD"])
             
                 # Verify create_default_engine was called (proving auto-scan triggered)
                 assert mock_create_engine.called
                 assert result.exit_code == 0

    def test_git_diff_integration(self, runner, mock_engine):
        """Test that git diff arguments are passed correctly."""
        with patch("jnkn.cli.commands.check.get_changed_files_from_git") as mock_git:
            mock_git.return_value = []
            
            runner.invoke(check, ["--git-diff", "origin/main", "feature-branch"])
            
            mock_git.assert_called_once_with("origin/main", "feature-branch")

    def test_diff_file_input(self, runner, mock_engine):
        """Test that --diff file input is handled."""
        with patch("jnkn.cli.commands.check.get_changed_files_from_diff_file") as mock_diff_file:
            # Mock file existence logic is handled by click, but we use isolated filesystem
            with runner.isolated_filesystem():
                with open("changes.diff", "w") as f:
                    f.write("diff --git a/file.py b/file.py")
                
                mock_diff_file.return_value = []
                
                runner.invoke(check, ["--diff", "changes.diff"])
                
                mock_diff_file.assert_called_once_with("changes.diff")