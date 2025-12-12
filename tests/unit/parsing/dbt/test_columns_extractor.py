"""
Unit tests for the dbt Column Lineage Extractor.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.dbt.extractors.columns import DbtColumnExtractor

@pytest.fixture
def mock_sqlglot_classes():
    """
    Mock sqlglot.exp classes using real types so isinstance checks pass.
    """
    class MockSelect: 
        def __init__(self):
            self.expressions = []
            
    class MockColumn:
        def __init__(self):
            self.name = ""
            
    class MockAlias:
        def __init__(self):
            self.alias = ""

    return MockSelect, MockColumn, MockAlias

@pytest.fixture
def mock_sqlglot(mock_sqlglot_classes):
    """Mock sqlglot to avoid hard dependency in unit tests."""
    MockSelect, MockColumn, MockAlias = mock_sqlglot_classes
    
    with patch("jnkn.parsing.dbt.extractors.columns.sqlglot") as mock_lib, \
         patch("jnkn.parsing.dbt.extractors.columns.exp") as mock_exp:
        
        # Assign the dummy classes to the mock module
        mock_exp.Select = MockSelect
        mock_exp.Column = MockColumn
        mock_exp.Alias = MockAlias
        
        # Create a mock return value for parse_one
        mock_parsed = MockSelect()
        mock_lib.parse_one.return_value = mock_parsed
        
        yield mock_lib, mock_parsed, mock_exp

def test_sanitize_jinja():
    extractor = DbtColumnExtractor()
    
    raw = """
    {{ config(materialized='table') }}
    select * from {{ ref('users') }}
    left join {{ source('raw', 'events') }} as e
    """
    
    clean = extractor._sanitize_jinja(raw)
    
    assert "{{ config" not in clean
    assert "users" in clean
    assert "{{ ref" not in clean
    assert "raw.events" in clean
    assert "{{ source" not in clean

def test_extract_columns_with_mock(mock_sqlglot):
    mock_lib, mock_parsed, mock_exp = mock_sqlglot
    
    # 1. Setup the Parsed SQL Object
    # Create column expression
    c1 = mock_exp.Column()
    c1.name = "user_id"
    
    # Create alias expression
    c2 = mock_exp.Alias()
    c2.alias = "user_email"
    
    mock_parsed.expressions = [c1, c2]
    
    # 2. Run Extractor
    ctx = ExtractionContext(
        file_path=Path("models/dim_users.sql"),
        file_id="file://models/dim_users.sql",
        text="SELECT user_id, email as user_email FROM users"
    )
    
    extractor = DbtColumnExtractor()
    
    # Force available to True for test
    with patch("jnkn.parsing.dbt.extractors.columns.SQLGLOT_AVAILABLE", True):
        results = list(extractor.extract(ctx))
        
        nodes = [r for r in results if isinstance(r, Node)]
        edges = [r for r in results if isinstance(r, Edge)]
        
        assert len(nodes) == 2
        
        # Verify Column Nodes
        assert any(n.id == "column:dim_users/user_id" for n in nodes)
        assert any(n.id == "column:dim_users/user_email" for n in nodes)
        
        # Verify Edges (Model CONTAINS Column)
        assert len(edges) == 2
        assert edges[0].source_id == "data:model:dim_users"
        assert edges[0].target_id == "column:dim_users/user_id"
        assert edges[0].type == RelationshipType.CONTAINS