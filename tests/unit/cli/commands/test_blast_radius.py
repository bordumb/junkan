"""
Unit tests for the 'blast-radius' command.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from jnkn.cli.commands.blast_radius import blast_radius

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
        """Test that --json bypasses the formatter."""
        runner = CliRunner()
        
        mock_graph = MagicMock()
        mock_graph.has_node.return_value = True
        mock_load.return_value = mock_graph

        mock_analyzer = mock_analyzer_cls.return_value
        # UPDATED: Mock result must match BlastRadiusResponse schema
        mock_result = {
            "source_artifacts": ["env:TEST"],
            "impacted_artifacts": ["file://a.py"],
            "count": 1,
            "breakdown": {"code": ["file://a.py"]}
        }
        mock_analyzer.calculate.return_value = mock_result

        result = runner.invoke(blast_radius, ["env:TEST", "--json"])

        assert result.exit_code == 0
        # Check for specific data in the JSON envelope
        assert "file://a.py" in result.output
        assert "impacted_artifacts" in result.output

    @patch("jnkn.cli.commands.blast_radius.load_graph")
    def test_blast_radius_node_resolution_failure(self, mock_load):
        """Test behavior when node cannot be resolved."""
        runner = CliRunner()
        
        mock_graph = MagicMock()
        mock_graph.has_node.return_value = False
        mock_graph.find_nodes.return_value = [] # Fuzzy search fails
        mock_load.return_value = mock_graph

        result = runner.invoke(blast_radius, ["ghost_node"])
        
        assert result.exit_code == 0
        assert "Artifact not found: ghost_node" in result.output