"""
Unit tests for OpenLineage Extractors.
"""

import json
from pathlib import Path
import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.openlineage.extractors.jobs import JobExtractor
from jnkn.parsing.openlineage.extractors.datasets import DatasetExtractor
from jnkn.parsing.openlineage.extractors.columns import ColumnExtractor

@pytest.fixture
def make_context():
    def _make(data: dict | list):
        return ExtractionContext(
            file_path=Path("event.json"),
            file_id="file://event.json",
            text=json.dumps(data)
        )
    return _make

class TestJobExtractor:
    def test_extract_job(self, make_context):
        event = {
            "eventType": "COMPLETE",
            "eventTime": "2024-01-01T00:00:00Z",
            "job": {"namespace": "spark", "name": "daily_etl"},
            "run": {"runId": "123"}
        }
        extractor = JobExtractor()
        assert extractor.can_extract(make_context(event))
        
        results = list(extractor.extract(make_context(event)))
        
        node = next(r for r in results if isinstance(r, Node))
        assert node.id == "job:spark/daily_etl"
        assert node.type == NodeType.JOB
        assert node.metadata["run_id"] == "123"
        
        edge = next(r for r in results if isinstance(r, Edge))
        assert edge.target_id == "job:spark/daily_etl"

    def test_ignore_start_event(self, make_context):
        event = {"eventType": "START", "job": {"namespace": "a", "name": "b"}}
        extractor = JobExtractor()
        results = list(extractor.extract(make_context(event)))
        assert len(results) == 0

class TestDatasetExtractor:
    def test_extract_inputs_outputs(self, make_context):
        event = {
            "eventType": "COMPLETE",
            "job": {"namespace": "ns", "name": "job1"},
            "inputs": [{"namespace": "db", "name": "users"}],
            "outputs": [{"namespace": "s3", "name": "bucket/data"}]
        }
        extractor = DatasetExtractor()
        results = list(extractor.extract(make_context(event)))
        
        nodes = [r for r in results if isinstance(r, Node)]
        edges = [r for r in results if isinstance(r, Edge)]
        
        # Verify Nodes
        assert any(n.id == "data:db/users" for n in nodes)
        assert any(n.id == "data:s3/bucket/data" for n in nodes)
        
        # Verify Edges
        # Job READS Input
        read_edge = next(e for e in edges if e.type == RelationshipType.READS)
        assert read_edge.source_id == "job:ns/job1"
        assert read_edge.target_id == "data:db/users"
        
        # Job WRITES Output
        write_edge = next(e for e in edges if e.type == RelationshipType.WRITES)
        assert write_edge.source_id == "job:ns/job1"
        assert write_edge.target_id == "data:s3/bucket/data"

class TestColumnExtractor:
    def test_extract_schema_and_lineage(self, make_context):
        event = {
            "eventType": "COMPLETE",
            "outputs": [{
                "namespace": "db", "name": "target_table",
                "facets": {
                    "schema": {
                        "fields": [{"name": "id", "type": "INT"}]
                    },
                    "columnLineage": {
                        "fields": {
                            "id": {
                                "inputFields": [
                                    {"namespace": "db", "name": "src_table", "field": "user_id"}
                                ]
                            }
                        }
                    }
                }
            }]
        }
        extractor = ColumnExtractor()
        results = list(extractor.extract(make_context(event)))
        
        nodes = [r for r in results if isinstance(r, Node)]
        edges = [r for r in results if isinstance(r, Edge) and r.type == RelationshipType.TRANSFORMS]
        
        # Check Column Node
        col_node = next(n for n in nodes if n.name == "id")
        assert col_node.id == "column:db/target_table/id"
        assert col_node.metadata["data_type"] == "INT"
        
        # Check Transformation Edge
        assert len(edges) == 1
        assert edges[0].source_id == "column:db/src_table/user_id"
        assert edges[0].target_id == "column:db/target_table/id"