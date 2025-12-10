"""Unit tests for CLI utilities."""

from unittest.mock import patch, MagicMock
from pathlib import Path
import json
import pytest
from jnkn.cli.utils import load_graph, echo_low_node_warning

class TestUtils:
    def test_load_graph_from_json(self, tmp_path):
        f = tmp_path / "graph.json"
        f.write_text(json.dumps({"nodes": [], "edges": []}))
        
        graph = load_graph(str(f))
        assert graph is not None

    def test_load_graph_from_directory(self, tmp_path):
        jnkn_dir = tmp_path / ".jnkn"
        jnkn_dir.mkdir()
        f = jnkn_dir / "lineage.json"
        f.write_text(json.dumps({"nodes": [], "edges": []}))
        
        # Pass directory, expect it to find .jnkn/lineage.json
        graph = load_graph(str(tmp_path))
        assert graph is not None

    def test_load_graph_missing(self, tmp_path, capsys):
        graph = load_graph(str(tmp_path / "missing.json"))
        assert graph is None
        captured = capsys.readouterr()
        assert "Graph file not found" in captured.err