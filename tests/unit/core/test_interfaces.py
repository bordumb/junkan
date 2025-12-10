"""
Tests for Core Interfaces and Refactored Graph.
"""

import pytest
from jnkn.core.graph import DependencyGraph
from jnkn.core.types import Node, Edge, NodeType, RelationshipType

def test_graph_implements_protocol():
    """Verify DependencyGraph implements IGraph protocol at runtime."""
    # Static checking is done by mypy, but we can verify methods exist
    g = DependencyGraph()
    assert hasattr(g, "add_node")
    assert hasattr(g, "get_out_edges")
    assert hasattr(g, "trace")

def test_graph_edge_retrieval():
    """Verify the new get_out/in_edges methods required by Trace command."""
    g = DependencyGraph()
    n1 = Node(id="A", name="A", type=NodeType.CODE_FILE)
    n2 = Node(id="B", name="B", type=NodeType.ENV_VAR)
    
    g.add_node(n1)
    g.add_node(n2)
    
    e = Edge(source_id="A", target_id="B", type=RelationshipType.READS)
    g.add_edge(e)
    
    # Check Out Edges
    out_edges = g.get_out_edges("A")
    assert len(out_edges) == 1
    assert out_edges[0].target_id == "B"
    assert out_edges[0].type == RelationshipType.READS
    
    # Check In Edges
    in_edges = g.get_in_edges("B")
    assert len(in_edges) == 1
    assert in_edges[0].source_id == "A"
    
    # Check Missing
    assert g.get_out_edges("B") == []

def test_trace_via_interface():
    """Verify trace works via the interface wrapper."""
    g = DependencyGraph()
    n1 = Node(id="A", name="A", type=NodeType.CODE_FILE)
    n2 = Node(id="B", name="B", type=NodeType.ENV_VAR)
    g.add_node(n1)
    g.add_node(n2)
    g.add_edge(Edge(source_id="A", target_id="B", type=RelationshipType.READS))
    
    paths = g.trace("A", "B")
    assert len(paths) == 1
    assert paths[0] == ["A", "B"]