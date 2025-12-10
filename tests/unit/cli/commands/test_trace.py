"""
Unit tests for the 'trace' command.
"""

from unittest.mock import MagicMock, patch
import pytest
from click.testing import CliRunner

from jnkn.cli.commands.trace import trace
from jnkn.core.types import Node, NodeType

class TestTraceCommand:
    """Tests for the lineage trace CLI command."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_graph(self):
        """
        Creates a mock DependencyGraph with predictable behavior.
        """
        graph = MagicMock()
        graph.has_node.return_value = True
        graph.find_nodes.return_value = []
        graph.trace.return_value = [] # Default: no standard path
        
        # Mock Graph Internal APIs for Semantic BFS
        graph.get_out_edges.return_value = []
        graph.get_in_edges.return_value = []
        
        def get_node_side_effect(node_id):
            return Node(id=node_id, name=node_id.upper(), type=NodeType.UNKNOWN)
        
        graph.get_node.side_effect = get_node_side_effect
        return graph

    @patch("jnkn.cli.commands.trace.load_graph")
    def test_trace_graph_load_failure(self, mock_load, runner):
        """Test that command exits gracefully if graph cannot be loaded."""
        mock_load.return_value = None
        result = runner.invoke(trace, ["src", "tgt"])
        assert result.exit_code == 0

    @patch("jnkn.cli.commands.trace._semantic_bfs")
    @patch("jnkn.cli.commands.trace.load_graph")
    def test_trace_success_path_found(self, mock_load, mock_bfs, runner, mock_graph):
        """Test a successful trace where a path exists."""
        mock_load.return_value = mock_graph
        
        # Mock the semantic BFS to return a path directly
        mock_bfs.return_value = [["node:a", "node:b", "node:c"]]
        
        result = runner.invoke(trace, ["node:a", "node:c"])
        
        assert result.exit_code == 0
        assert "Lineage Trace" in result.output
        assert "From: node:a" in result.output
        assert "1 path(s) found" in result.output
        assert "NODE:B" in result.output

    @patch("jnkn.cli.commands.trace._semantic_bfs")
    @patch("jnkn.cli.commands.trace.load_graph")
    def test_trace_reverse_path_fallback(self, mock_load, mock_bfs, runner, mock_graph):
        """Test that if forward path fails, it attempts a reverse trace."""
        mock_load.return_value = mock_graph
        
        # 1. Semantic BFS fails
        mock_bfs.return_value = []
        
        # 2. Standard Trace (called in fallback) fails? No, we call graph.trace in fallback logic
        # Setup: Reverse (B->A) succeeds
        def trace_side_effect(src, tgt):
            if src == "node:b" and tgt == "node:a":
                return [["node:b", "node:a"]]
            return []
            
        mock_graph.trace.side_effect = trace_side_effect
        
        result = runner.invoke(trace, ["node:a", "node:b"])
        
        assert result.exit_code == 0
        # FIXED: Match the new output string
        assert "Found dependency path (Consumer -> Provider)" in result.output
        # And ensure the visual is reversed (From: node:a, To: node:b)
        assert "From: node:a" in result.output

    @patch("jnkn.cli.commands.trace._semantic_bfs")
    @patch("jnkn.cli.commands.trace.load_graph")
    def test_trace_no_path_found(self, mock_load, mock_bfs, runner, mock_graph):
        """Test output when no path exists in either direction."""
        mock_load.return_value = mock_graph
        mock_bfs.return_value = []
        mock_graph.trace.return_value = []
        
        result = runner.invoke(trace, ["node:a", "node:b"])
        
        assert result.exit_code == 0
        assert "No path found" in result.output

    @patch("jnkn.cli.commands.trace.load_graph")
    def test_resolve_node_failure(self, mock_load, runner, mock_graph):
        mock_load.return_value = mock_graph
        mock_graph.has_node.return_value = False
        mock_graph.find_nodes.return_value = []
        
        result = runner.invoke(trace, ["ghost", "target"])
        assert "No node found matching source: ghost" in result.output