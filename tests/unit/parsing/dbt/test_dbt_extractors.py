"""
Unit tests for DBT Extractors.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.dbt.extractors.sql_files import SQLFileExtractor
from jnkn.parsing.dbt.extractors.schema_yaml import SchemaYamlExtractor

@pytest.fixture
def make_context():
    def _make(text: str, path: str = "models/my_model.sql"):
        return ExtractionContext(
            file_path=Path(path),
            file_id=f"file://{path}",
            text=text
        )
    return _make

class TestSQLFileExtractor:
    def test_extract_simple_model(self, make_context):
        text = """
        {{ config(materialized='table') }}
        select * from {{ ref('staging_users') }}
        """
        extractor = SQLFileExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        # Check Model Node
        node = next(r for r in results if isinstance(r, Node))
        assert node.id == "data:model:my_model"
        assert node.metadata["materialized"] == "table"
        assert node.metadata["from_sql"] is True
        
        # Check Edges
        # 1. File -> Model (Contains)
        # 2. Model -> Ref (Depends On)
        edges = [r for r in results if isinstance(r, Edge)]
        
        ref_edge = next(e for e in edges if e.type == RelationshipType.DEPENDS_ON)
        assert ref_edge.source_id == "data:model:my_model"
        assert ref_edge.target_id == "data:model:staging_users"
        assert ref_edge.metadata["type"] == "ref"

    def test_extract_source(self, make_context):
        text = "select * from {{ source('raw', 'events') }}"
        extractor = SQLFileExtractor()
        results = list(extractor.extract(make_context(text)))
        
        edges = [r for r in results if isinstance(r, Edge) and r.type == RelationshipType.READS]
        source_edge = edges[0]
        assert source_edge.target_id == "data:source:raw.events"
        assert source_edge.metadata["type"] == "source"

    def test_can_extract_checks(self, make_context):
        extractor = SQLFileExtractor()
        # Wrong extension
        assert not extractor.can_extract(make_context("{{ ref('x') }}", "test.py"))
        # No jinja
        assert not extractor.can_extract(make_context("select * from table"))

class TestSchemaYamlExtractor:
    def test_extract_models_and_tests(self, make_context):
        text = """
        version: 2
        models:
          - name: customers
            description: "Customer table"
            columns:
              - name: id
                tests:
                  - unique
                  - not_null
        """
        extractor = SchemaYamlExtractor()
        # Mock yaml import check if needed, but assuming PyYAML is installed for tests
        assert extractor.can_extract(make_context(text, "schema.yml"))
        
        results = list(extractor.extract(make_context(text, "schema.yml")))
        
        nodes = [r for r in results if isinstance(r, Node)]
        edges = [r for r in results if isinstance(r, Edge)]
        
        # Check Model Node
        model_node = next(n for n in nodes if n.type == NodeType.DATA_ASSET)
        assert model_node.id == "data:model:customers"
        assert model_node.metadata["description"] == "Customer table"
        
        # Check Test Nodes (unique, not_null)
        test_nodes = [n for n in nodes if n.type == NodeType.JOB]
        assert len(test_nodes) == 2
        assert any(n.metadata["test_type"] == "unique" for n in test_nodes)
        
        # Check Edges (Test -> Model)
        assert len(edges) == 2
        assert all(e.type == RelationshipType.DEPENDS_ON for e in edges)
        assert all(e.target_id == "data:model:customers" for e in edges)

    def test_extract_sources(self, make_context):
        text = """
        version: 2
        sources:
          - name: stripe
            database: raw
            tables:
              - name: charges
                freshness:
                  warn_after: {count: 12, period: hour}
        """
        extractor = SchemaYamlExtractor()
        results = list(extractor.extract(make_context(text, "sources.yaml")))
        
        nodes = [r for r in results if isinstance(r, Node)]
        source_node = nodes[0]
        assert source_node.id == "data:source:stripe.charges"
        assert source_node.metadata["resource_type"] == "source"
        assert source_node.metadata["database"] == "raw"

    def test_invalid_yaml(self, make_context):
        extractor = SchemaYamlExtractor()
        # Invalid YAML syntax
        results = list(extractor.extract(make_context("key: value: error", "test.yml")))
        assert len(results) == 0
        
        # Valid YAML but not a dict
        results_list = list(extractor.extract(make_context("- list item", "test.yml")))
        assert len(results_list) == 0