"""Unit tests for the Lineage Graph module."""

import json
from pathlib import Path
import pytest
from jnkn.graph.lineage import LineageGraph
# Updated import
from jnkn.cli.commands.blast_radius import _resolve_node_id


class TestLineageGraph:
    def test_add_node_and_edge(self):
        g = LineageGraph()
        g.add_node("A", name="Node A")
        g.add_node("B", name="Node B")
        g.add_edge("A", "B", "writes")
        
        assert g.get_node("A")["name"] == "Node A"
        assert g.stats()["total_nodes"] == 2
        assert g.stats()["total_edges"] == 1

    def test_downstream_traversal(self):
        g = LineageGraph()
        g.add_edge("A", "B", "provides")
        g.add_edge("C", "B", "reads")
        
        downstream = g.downstream("A")
        assert "B" in downstream
        assert "C" in downstream
        
    def test_json_roundtrip(self):
        g = LineageGraph()
        g.add_node("A")
        json_str = g.to_json()
        
        g2 = LineageGraph()
        g2.load_from_json(json_str)
        assert g2.has_node("A")


class TestLineageTraversal:
    def test_mixed_direction_impact(self):
        g = LineageGraph()
        g.add_node("infra:output:db_host")
        g.add_node("env:DB_HOST")
        g.add_edge("infra:output:db_host", "env:DB_HOST", "provides")
        g.add_node("file://src/app.py")
        g.add_edge("file://src/app.py", "env:DB_HOST", "reads")
        
        impacted = g.downstream("infra:output:db_host")
        
        assert "env:DB_HOST" in impacted
        assert "file://src/app.py" in impacted
        assert len(impacted) == 2

    def test_upstream_root_cause(self):
        g = LineageGraph()
        g.add_node("infra:output:db_host")
        g.add_node("env:DB_HOST")
        g.add_edge("infra:output:db_host", "env:DB_HOST", "provides")
        g.add_node("file://src/app.py")
        g.add_edge("file://src/app.py", "env:DB_HOST", "reads")
        
        roots = g.upstream("file://src/app.py")
        
        assert "env:DB_HOST" in roots
        assert "infra:output:db_host" in roots

    def test_terraform_chain(self):
        g = LineageGraph()
        g.add_edge("infra:aws_db_instance.main", "infra:output:db_host", "provisions")
        g.add_edge("infra:output:db_host", "env:DB_HOST", "provides")
        g.add_edge("file://app.py", "env:DB_HOST", "reads")
        
        impacted = g.downstream("infra:aws_db_instance.main")
        
        assert "infra:output:db_host" in impacted
        assert "env:DB_HOST" in impacted
        assert "file://app.py" in impacted


class TestArtifactResolution:
    class MockGraph:
        def __init__(self, nodes):
            self.nodes = set(nodes)
        
        def has_node(self, node_id):
            return node_id in self.nodes
            
        def find_nodes(self, pattern):
            return [n for n in self.nodes if pattern in n]

    def test_resolve_terraform_dot_syntax(self):
        """Test resolving infra:output.name to infra:output:name."""
        graph = self.MockGraph(["infra:output:payment_db_host"])
        
        user_input = "infra:output.payment_db_host"
        
        resolved = _resolve_node_id(graph, user_input)
        assert resolved == "infra:output:payment_db_host"

    def test_resolve_infra_general_dot_syntax(self):
        """Test resolving general infra resource dots to colons."""
        graph = self.MockGraph(["infra:aws_db_instance:main"])
        
        user_input = "infra:aws_db_instance.main"
        
        resolved = _resolve_node_id(graph, user_input)
        assert resolved == "infra:aws_db_instance:main"

    def test_resolve_prefix_addition(self):
        """Test matching partial name 'DB_HOST' to 'env:DB_HOST'."""
        graph = self.MockGraph(["env:DB_HOST", "file://app.py"])
        
        resolved = _resolve_node_id(graph, "DB_HOST")
        assert resolved == "env:DB_HOST"

    def test_fuzzy_search(self):
        """Test finding file by partial path."""
        graph = self.MockGraph(["file:///abs/path/to/src/app.py"])
        
        resolved = _resolve_node_id(graph, "src/app.py")
        assert resolved == "file:///abs/path/to/src/app.py"