"""
Unit tests for the visualization module.
"""

from unittest.mock import MagicMock
import pytest
import json
import re
from jnkn.graph.visualize import generate_html
from jnkn.core.types import Node, Edge, NodeType, RelationshipType

class TestVisualize:
    @pytest.fixture
    def mock_graph(self):
        """Create a mock IGraph with diverse node and edge types."""
        graph = MagicMock()
        
        # Mock iter_nodes
        # Note: Using 'env_var' as the value to ensure it matches the checks
        nodes = [
            Node(id="env:DB_HOST", name="DB_HOST", type=NodeType.ENV_VAR),
            Node(id="infra:aws_db_instance.main", name="main", type=NodeType.INFRA_RESOURCE),
            Node(id="file://app.py", name="app.py", type=NodeType.CODE_FILE)
        ]
        graph.iter_nodes.return_value = nodes
        
        # Mock iter_edges
        edges = [
            Edge(source_id="infra:aws_db_instance.main", target_id="env:DB_HOST", type=RelationshipType.PROVIDES),
            Edge(source_id="file://app.py", target_id="env:DB_HOST", type=RelationshipType.READS)
        ]
        graph.iter_edges.return_value = edges
        
        # Mock to_dict (optional but preferred path)
        graph.to_dict.return_value = {
            "nodes": [n.model_dump() for n in nodes],
            "edges": [e.model_dump() for e in edges]
        }
        
        return graph

    def test_generate_html_structure(self, mock_graph):
        """
        Test that HTML contains essential structure and data.
        """
        html = generate_html(mock_graph)
        
        assert "<!DOCTYPE html>" in html
        assert "vis.DataSet" in html
        
        # 1. Verify Node Data is embedded
        # We check for the raw ID and Type, which Python injects into __GRAPH_DATA__
        assert 'id": "env:DB_HOST"' in html
        # Pydantic serialization of the Enum might differ (value vs name), 
        # but one of these strings should be present in the JSON blob.
        assert 'env_var' in html or 'ENV_VAR' in html
        
        # 2. Verify Edge Data is embedded
        assert 'source_id": "infra:aws_db_instance.main"' in html
        assert 'provides' in html

        # 3. Verify JS Logic exists
        # We don't check for "group": "config" because that is calculated by the browser.
        # Instead, we check that the logic function is present.
        assert "function inferGroup(type, id)" in html
        assert "return 'config'" in html

    def test_javascript_traversal_logic_exists(self, mock_graph):
        """
        Verify that the JS traversal logic includes the semantic sets.
        """
        html = generate_html(mock_graph)
        
        # Check for Forward Impact Types
        assert "FORWARD_IMPACT_TYPES = new Set" in html
        assert "'provides'" in html
        
        # Check for Reverse Impact Types
        assert "REVERSE_IMPACT_TYPES = new Set" in html
        assert "'reads'" in html

    def test_edge_visual_properties(self, mock_graph):
        """Test that edges get correct visual properties."""
        html = generate_html(mock_graph)
        
        # Check that the JS code responsible for dashing edges is present
        # This confirms the visual logic was injected
        assert "dashes: REVERSE_IMPACT_TYPES.has" in html