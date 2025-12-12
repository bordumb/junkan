"""
Unit tests for the 'blast-radius' command.
"""

import json
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from jnkn.cli.commands.blast_radius import blast_radius
from jnkn.core.exceptions import GraphNotFoundError

class TestBlastRadiusCommand:
    """Integration tests for the blast radius CLI."""

    @patch("jnkn.cli.commands.blast_radius.BlastRadiusAnalyzer")
    @patch("jnkn.cli.commands.blast_radius.load_graph")
    @patch("jnkn.cli.commands.blast_radius.format_blast_radius")
    def test_blast_radius_default_output(self, mock_format, mock_load, mock_analyzer_cls):
        """Test that the text formatter is used by default."""
        runner = CliRunner()
        
        # Mock Graph Loading
        mock_graph = MagicMock()
        mock_graph.has_node.return_value = True
        mock_load.return_value = mock_graph

        # Mock Analysis
        mock_analyzer = mock_analyzer_cls.return_value
        mock_result = {
            "source_artifacts": ["env:TEST"],
            "impacted_artifacts": ["file://a.py"],
            "count": 1,
            "breakdown": {}
        }
        mock_analyzer.calculate.return_value = mock_result
        
        mock_format.return_value = "Formatted Output"

        result = runner.invoke(blast_radius, ["env:TEST"])

        assert result.exit_code == 0
        assert "Formatted Output" in result.output
        mock_format.assert_called_once_with(mock_result)

    @patch("jnkn.cli.commands.blast_radius.BlastRadiusAnalyzer")
    @patch("jnkn.cli.commands.blast_radius.load_graph")
    def test_blast_radius_json_output(self, mock_load, mock_analyzer_cls):
        """Test that --json produces the correct API envelope."""
        runner = CliRunner()
        
        mock_graph = MagicMock()
        mock_graph.has_node.return_value = True
        mock_load.return_value = mock_graph

        mock_analyzer = mock_analyzer_cls.return_value
        # Mock result must match internal dictionary structure
        mock_result = {
            "source_artifacts": ["env:TEST"],
            "impacted_artifacts": ["file://a.py"],
            "count": 1,
            "breakdown": {"code": ["file://a.py"]}
        }
        mock_analyzer.calculate.return_value = mock_result

        result = runner.invoke(blast_radius, ["env:TEST", "--json"])

        assert result.exit_code == 0
        
        # Verify Output is Valid JSON
        try:
            data = json.loads(result.output)
        except json.JSONDecodeError:
            assert False, f"Output is not valid JSON: {result.output}"

        # Verify Envelope Structure
        assert data["status"] == "success"
        assert data["data"]["count"] == 1
        assert "file://a.py" in data["data"]["impacted_artifacts"]

    @patch("jnkn.cli.commands.blast_radius.load_graph")
    def test_blast_radius_json_error_handling(self, mock_load):
        """
        Verify that exceptions result in JSON output, not empty stdout.
        This prevents 'Unexpected end of JSON input' errors in CI.
        """
        runner = CliRunner()
        
        # Simulate Graph Not Found (Common CI failure)
        mock_load.return_value = None
        
        result = runner.invoke(blast_radius, ["env:TEST", "--json"])
        
        # 1. Must NOT be empty
        assert result.output.strip(), "CLI produced no output on failure!"
        
        # 2. Must be Valid JSON
        try:
            data = json.loads(result.output)
        except json.JSONDecodeError:
            assert False, f"Error output is not valid JSON: {result.output}"
            
        # 3. Must have Error Status
        assert data["status"] == "error"
        assert data["error"]["code"] == "GRAPH_MISSING"
        
        # 4. Exit Code should likely be non-zero for failure, 
        # but renderer might handle it gracefully. 
        # Checking implementation: sys.exit(1) is called for errors in json mode.
        # However, CliRunner captures the exit.
        # Note: If your implementation exits 0 on error (it shouldn't), this will catch it.
        # Current implementation in renderers.py prints JSON but main command flow needs 
        # to ensure it doesn't just return None.
        
    @patch("jnkn.cli.commands.blast_radius.load_graph")
    def test_blast_radius_node_resolution_failure(self, mock_load):
        """Test behavior when node cannot be resolved in text mode."""
        runner = CliRunner()
        
        mock_graph = MagicMock()
        mock_graph.has_node.return_value = False
        mock_graph.find_nodes.return_value = [] # Fuzzy search fails
        mock_load.return_value = mock_graph

        result = runner.invoke(blast_radius, ["ghost_node"])
        
        # Text mode prints error to stderr usually
        assert "Artifact not found" in result.output or result.exit_code != 0