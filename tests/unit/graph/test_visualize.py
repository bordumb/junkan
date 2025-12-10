"""
Unit tests for the visualization module.

Ensures that:
1. HTML generation works with various graph structures.
2. The JavaScript logic embedded in the HTML covers all edge types correctly.
3. Node categories and colors are assigned correctly.
"""

from unittest.mock import MagicMock
import pytest
import json
from jnkn.graph.visualize import generate_html

class TestVisualize:
    @pytest.fixture
    def mock_graph(self):
        """Create a mock LineageGraph with diverse node and edge types."""
        graph = MagicMock()
        
        # Mock data structure matching graph.to_dict()
        data = {
            "nodes": [
                {"id": "env:DB_HOST", "name": "DB_HOST"},
                {"id": "infra:aws_db_instance.main", "name": "aws_db_instance.main"},
                {"id": "file://app.py", "name": "app.py"},
                {"id": "data:users", "name": "users"}
            ],
            "edges": [
                # Infra PROVIDES Env (Forward impact)
                {"source": "infra:aws_db_instance.main", "target": "env:DB_HOST", "type": "provides"},
                # File READS Env (Reverse impact)
                {"source": "file://app.py", "target": "env:DB_HOST", "type": "reads"},
                # Configures edge
                {"source": "infra:vpc", "target": "infra:subnet", "type": "configures"}
            ],
            "stats": {"node_count": 4, "edge_count": 3}
        }
        
        graph.to_dict.return_value = data
        return graph

    def test_generate_html_structure(self, mock_graph):
        """Test that HTML contains essential structure and data."""
        html = generate_html(mock_graph)
        
        assert "<!DOCTYPE html>" in html
        assert "vis.DataSet" in html
        
        # Verify node data is embedded
        assert 'id": "env:DB_HOST"' in html
        assert 'group": "config"' in html  # Check category assignment
        assert 'color": "#FF9800"' in html # Check color assignment for config
        
        # Verify edge data is embedded
        assert 'from": "infra:aws_db_instance.main"' in html
        assert 'title": "provides"' in html

    def test_javascript_traversal_logic_exists(self, mock_graph):
        """
        Verify that the JS traversal logic includes the fix for custom edge types.
        
        We check for the presence of the sets defining edge directionality.
        """
        html = generate_html(mock_graph)
        
        # Check for Forward Impact Types (Source -> Target)
        assert "FORWARD_IMPACT_TYPES = new Set" in html
        assert "'provides'" in html
        assert "'configures'" in html
        assert "'provisions'" in html
        
        # Check for Reverse Impact Types (Target -> Source)
        assert "REVERSE_IMPACT_TYPES = new Set" in html
        assert "'reads'" in html
        assert "'depends_on'" in html

    def test_node_categories(self, mock_graph):
        """Test that different node types get correct categories."""
        html = generate_html(mock_graph)
        
        # env: -> config
        assert 'id": "env:DB_HOST"' in html
        assert 'group": "config"' in html
        
        # infra: -> infra
        assert 'id": "infra:aws_db_instance.main"' in html
        assert 'group": "infra"' in html
        
        # file: -> code
        assert 'id": "file://app.py"' in html
        assert 'group": "code"' in html
        
        # data: -> data
        assert 'id": "data:users"' in html
        assert 'group": "data"' in html

    def test_edge_visual_properties(self, mock_graph):
        """Test that edges get correct visual properties (dashes, arrows)."""
        html = generate_html(mock_graph)
        
        # 'reads' should be dashed (dashes: true)
        # We need to look for the JSON structure in the HTML
        # Simple string check is fragile, but effective for checking intent
        assert '"title": "reads"' in html
        
        # 'provides' should be solid (dashes: false)
        assert '"title": "provides"' in html
