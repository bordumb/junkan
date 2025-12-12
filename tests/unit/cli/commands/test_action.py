"""
Comprehensive unit tests for the 'action' CI/CD command.

This suite verifies the end-to-end orchestration of the CI/CD workflow,
including scanning, stitching, checking, and reporting to GitHub.
"""

import json
from unittest.mock import MagicMock, patch, mock_open

import pytest
from click.testing import CliRunner, Result

from jnkn.cli.commands.action import action
from jnkn.core.result import Ok, Err
from jnkn.parsing.engine import ScanStats, ScanError


@pytest.fixture
def mock_dependencies():
    """
    Mock all external dependencies of the action command.
    
    Patches:
    - Parser Engine (Scan)
    - Storage (Graph persistence)
    - Stitcher (Graph linking)
    - CliRunner (Inner check command execution)
    - urllib (GitHub API interaction)
    - os.getenv (Environment variables)
    """
    with patch("jnkn.cli.commands.action.create_default_engine") as mock_engine, \
         patch("jnkn.cli.commands.action.SQLiteStorage") as mock_storage, \
         patch("jnkn.cli.commands.action.Stitcher") as mock_stitcher, \
         patch("click.testing.CliRunner") as mock_runner_cls, \
         patch("jnkn.cli.commands.action.urllib.request.urlopen") as mock_urlopen, \
         patch("jnkn.cli.commands.action.urllib.request.Request") as mock_request, \
         patch("jnkn.cli.commands.action.os.getenv") as mock_getenv:
        
        # Setup Engine (Scan)
        engine_instance = mock_engine.return_value
        stats = ScanStats(files_scanned=10)
        engine_instance.scan_and_store.return_value = Ok(stats)

        # Setup Storage
        storage_instance = mock_storage.return_value
        graph_mock = MagicMock()
        graph_mock.node_count = 5
        storage_instance.load_graph.return_value = graph_mock

        # Setup Stitcher
        stitcher_instance = mock_stitcher.return_value
        stitcher_instance.stitch.return_value = [MagicMock()] 

        # Setup Check Command Runner
        # We assume action.py calls click.testing.CliRunner() which returns this instance
        inner_runner_instance = mock_runner_cls.return_value
        
        # Default success response for 'check' command
        default_check_output = json.dumps({
            "data": {
                "critical_count": 0, 
                "high_count": 0, 
                "violations": [],
                "changed_files_count": 5
            }
        })
        
        # Mocking the Result object returned by invoke()
        success_result = MagicMock(spec=Result)
        success_result.exit_code = 0
        success_result.output = default_check_output
        success_result.stdout = default_check_output
        
        inner_runner_instance.invoke.return_value = success_result

        # Setup GitHub API responses
        # Context manager for urlopen
        mock_response = MagicMock()
        mock_response.read.return_value = b"[]"
        mock_response.status = 201
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Setup Env Vars (Default to GitHub Actions environment)
        def getenv_side_effect(key, default=None):
            if key == "GITHUB_REPOSITORY": return "owner/repo"
            if key == "GITHUB_EVENT_PATH": return "/event.json"
            return default
        mock_getenv.side_effect = getenv_side_effect

        yield {
            "engine": engine_instance,
            "storage": storage_instance,
            "stitcher": stitcher_instance,
            "inner_runner": inner_runner_instance,
            "urlopen": mock_urlopen,
            "request": mock_request,
            "getenv": mock_getenv
        }

@pytest.fixture
def mock_event_file():
    """Mock the GitHub event.json file."""
    event_data = {"pull_request": {"number": 123}}
    with patch("builtins.open", mock_open(read_data=json.dumps(event_data))):
        yield

class TestActionCommand:
    
    def test_full_success_flow(self, mock_dependencies, mock_event_file):
        """Test the happy path: Scan OK, Check OK, Comment Posted."""
        runner = CliRunner()
        result = runner.invoke(action, ["--token", "fake-token"])

        assert result.exit_code == 0
        assert "Scan failed" not in result.output
        assert "Check passed" in result.output
        
        # Verify Scan Called
        mock_dependencies["engine"].scan_and_store.assert_called_once()
        
        # Verify Stitching
        mock_dependencies["stitcher"].stitch.assert_called_once()
        mock_dependencies["storage"].save_edges_batch.assert_called_once()
        
        # Verify Check Command invoked
        mock_dependencies["inner_runner"].invoke.assert_called_once()
        args = mock_dependencies["inner_runner"].invoke.call_args[0][1]
        assert "--git-diff" in args
        assert "--json" in args

        # Verify GitHub Comment Posted
        assert mock_dependencies["urlopen"].call_count == 2
        assert "Posted PR comment" in result.output

    def test_scan_failure(self, mock_dependencies):
        """Test that action fails if scan fails."""
        mock_dependencies["engine"].scan_and_store.return_value = Err(ScanError("Parser exploded"))

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 1
        assert "Scan failed: Parser exploded" in result.output
        
        # Should NOT proceed to stitching or checking
        mock_dependencies["stitcher"].stitch.assert_not_called()
        mock_dependencies["inner_runner"].invoke.assert_not_called()

    def test_empty_graph_warning(self, mock_dependencies, mock_event_file):
        """Test warning when scan produces no nodes."""
        mock_dependencies["storage"].load_graph.return_value.node_count = 0

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 0  # Not a fatal error, just a warning
        assert "Graph is empty" in result.output
        
        # Stitcher should be skipped for empty graph
        mock_dependencies["stitcher"].stitch.assert_not_called()
        # Check should still run
        mock_dependencies["inner_runner"].invoke.assert_called()

    def test_check_internal_failure_invalid_json(self, mock_dependencies):
        """Test handling of 'jnkn check' returning garbage output."""
        failure = MagicMock(spec=Result)
        failure.exit_code = 1
        failure.output = "Traceback (most recent call last)..."
        mock_dependencies["inner_runner"].invoke.return_value = failure

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 1
        assert "Check command failed internally" in result.output
        assert "Traceback" in result.output

    def test_check_internal_failure_empty_json(self, mock_dependencies):
        """Test handling of 'jnkn check' returning valid JSON but missing data."""
        empty = MagicMock(spec=Result)
        empty.exit_code = 0
        empty.output = "{}"
        mock_dependencies["inner_runner"].invoke.return_value = empty

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 1
        assert "Failed to parse check results" in result.output

    def test_blocking_violation_critical(self, mock_dependencies, mock_event_file):
        """Test that critical violations block the build (default behavior)."""
        check_output = {
            "data": {
                "critical_count": 1,
                "high_count": 0,
                "violations": [{"severity": "critical", "rule": "R1", "message": "Bad"}]
            }
        }
        res = MagicMock(spec=Result)
        res.exit_code = 0
        res.output = json.dumps(check_output)
        mock_dependencies["inner_runner"].invoke.return_value = res

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 1
        assert "Blocking build: 1 critical" in result.output
        assert "Posted PR comment" in result.output

    def test_blocking_violation_high_config(self, mock_dependencies, mock_event_file):
        """Test that --fail-on=high blocks on high violations."""
        check_output = {
            "data": {
                "critical_count": 0,
                "high_count": 5,
                "violations": [{"severity": "high", "message": "Risky"}]
            }
        }
        res = MagicMock(spec=Result)
        res.exit_code = 0
        res.output = json.dumps(check_output)
        mock_dependencies["inner_runner"].invoke.return_value = res

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t", "--fail-on", "high"])

        assert result.exit_code == 1
        assert "Blocking build" in result.output
        assert "5 high violations" in result.output

    def test_non_blocking_violation(self, mock_dependencies, mock_event_file):
        """Test that high violations DO NOT block if fail-on=critical (default)."""
        check_output = {
            "data": {
                "critical_count": 0,
                "high_count": 5, # High risks exist
                "violations": []
            }
        }
        res = MagicMock(spec=Result)
        res.exit_code = 0
        res.output = json.dumps(check_output)
        mock_dependencies["inner_runner"].invoke.return_value = res

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t", "--fail-on", "critical"])

        assert result.exit_code == 0 # Should Pass
        assert "Check passed" in result.output

    def test_github_comment_update(self, mock_dependencies, mock_event_file):
        """Test updating an existing comment instead of creating a new one."""
        # Mock GET response containing an existing jnkn signature
        existing_comments = [
            {"id": 999, "body": "Old comment\n"} # Signature matching simplified for test
        ]
        
        # We need to simulate the sequence of API calls
        # 1. GET comments -> returns existing_comments
        # 2. PATCH comment -> returns success
        
        response_get = MagicMock()
        response_get.read.return_value = json.dumps(existing_comments).encode()
        response_get.status = 200
        
        response_patch = MagicMock()
        response_patch.read.return_value = b"{}"
        response_patch.status = 200
        
        mock_dependencies["urlopen"].side_effect = [
            MagicMock(__enter__=MagicMock(return_value=response_get)),
            MagicMock(__enter__=MagicMock(return_value=response_patch))
        ]

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 0
        assert "Updated PR comment" in result.output
        
        # Verify PATCH was used in the second call
        call_args = mock_dependencies["request"].call_args_list
        assert call_args[1].kwargs["method"] == "PATCH"
        assert "/999" in call_args[1].args[0]

    def test_github_env_missing(self, mock_dependencies):
        """Test behavior when running outside GitHub Actions (no env vars)."""
        # CRITICAL FIX: Explicitly clear the side_effect so return_value is respected
        mock_dependencies["getenv"].side_effect = None
        mock_dependencies["getenv"].return_value = None 

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 0
        assert "Not running in GitHub Actions context" in result.output
        assert mock_dependencies["urlopen"].call_count == 0

    def test_github_no_pr_number(self, mock_dependencies):
        """Test behavior when event.json exists but has no PR number."""
        with patch("builtins.open", mock_open(read_data=json.dumps({"push": {}}))):
            runner = CliRunner()
            result = runner.invoke(action, ["--token", "t"])

        assert result.exit_code == 0
        assert "No PR number found" in result.output
        assert mock_dependencies["urlopen"].call_count == 0

    def test_github_api_failure(self, mock_dependencies, mock_event_file):
        """Test graceful handling of GitHub API errors."""
        import urllib.error
        
        # Simulate API Error on POST
        response_get = MagicMock()
        response_get.read.return_value = b"[]"
        
        mock_dependencies["urlopen"].side_effect = [
            MagicMock(__enter__=MagicMock(return_value=response_get)),
            urllib.error.HTTPError("url", 500, "Server Error", {}, None)
        ]

        runner = CliRunner()
        result = runner.invoke(action, ["--token", "t"])

        # Should NOT crash the build, just log error
        assert result.exit_code == 0 
        assert "Error posting comment" in result.output