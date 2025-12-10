"""
Unit tests for the Diff Analyzer.
"""

import pytest
from jnkn.analysis.diff_analyzer import DiffAnalyzer, ChangeType
from jnkn.core.graph import DependencyGraph
from jnkn.core.types import Node, Edge, NodeType, RelationshipType

@pytest.fixture
def graph_pair():
    """Create two graphs representing a change state."""
    base = DependencyGraph()
    head = DependencyGraph()
    
    # Common node
    n1 = Node(id="env:DB", name="DB", type=NodeType.ENV_VAR)
    base.add_node(n1)
    head.add_node(n1)
    
    # Removed node (in base only)
    n2 = Node(id="infra:old", name="old", type=NodeType.INFRA_RESOURCE)
    base.add_node(n2)
    
    # Added node (in head only)
    n3 = Node(id="file://new.py", name="new.py", type=NodeType.CODE_FILE)
    head.add_node(n3)
    
    # Modified Node (same ID, different metadata)
    n4_base = Node(id="file://mod.py", name="mod.py", type=NodeType.CODE_FILE, metadata={"lines": 10})
    n4_head = Node(id="file://mod.py", name="mod.py", type=NodeType.CODE_FILE, metadata={"lines": 20})
    base.add_node(n4_base)
    head.add_node(n4_head)
    
    return base, head

def test_compare_nodes(graph_pair):
    base, head = graph_pair
    analyzer = DiffAnalyzer()
    
    report = analyzer.compare(base, head)
    
    # Check Added
    assert len(report.added_nodes) == 1
    assert report.added_nodes[0].name == "new.py"
    
    # Check Removed
    assert len(report.removed_nodes) == 1
    assert report.removed_nodes[0].name == "old"
    
    # Check Modified
    assert len(report.modified_nodes) == 1
    assert report.modified_nodes[0].id == "file://mod.py"
    
    # Check Breaking Change Detection
    # Removed infra:old is a breaking change heuristic
    assert report.has_breaking_changes is True

def test_compare_edges():
    base = DependencyGraph()
    head = DependencyGraph()
    
    # Nodes must exist for edges to be valid in rustworkx wrapper
    n1 = Node(id="A", name="A", type=NodeType.CODE_FILE)
    n2 = Node(id="B", name="B", type=NodeType.ENV_VAR)
    
    for g in [base, head]:
        g.add_node(n1)
        g.add_node(n2)
        
    # Edge in Base only (Removed)
    e1 = Edge(source_id="A", target_id="B", type=RelationshipType.READS)
    base.add_edge(e1)
    
    # Edge in Head only (Added) - distinct type to avoid confusion
    e2 = Edge(source_id="A", target_id="B", type=RelationshipType.WRITES)
    head.add_edge(e2)
    
    analyzer = DiffAnalyzer()
    report = analyzer.compare(base, head)
    
    assert len(report.edge_changes) == 2
    
    added = [e for e in report.edge_changes if e.change_type == ChangeType.ADDED]
    removed = [e for e in report.edge_changes if e.change_type == ChangeType.REMOVED]
    
    assert len(added) == 1
    assert added[0].type == RelationshipType.WRITES
    
    assert len(removed) == 1
    assert removed[0].type == RelationshipType.READS