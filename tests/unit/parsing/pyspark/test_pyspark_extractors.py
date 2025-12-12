"""
Unit tests for PySpark Extractors.
"""

from pathlib import Path
import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.pyspark.extractors.spark_config import SparkConfigExtractor
from jnkn.parsing.pyspark.extractors.delta import DeltaLakeExtractor

@pytest.fixture
def make_context():
    def _make(text: str):
        return ExtractionContext(
            file_path=Path("job.py"),
            file_id="file://job.py",
            text=text
        )
    return _make

class TestSparkConfigExtractor:
    def test_extract_conf_get(self, make_context):
        text = """
        val = spark.conf.get("spark.sql.shuffle.partitions")
        other = spark.conf.get("custom.property", "default")
        """
        extractor = SparkConfigExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        nodes = [r for r in results if isinstance(r, Node)]
        assert len(nodes) == 2
        assert nodes[0].id == "config:spark:spark.sql.shuffle.partitions"
        assert nodes[0].type == NodeType.CONFIG_KEY
        
        edges = [r for r in results if isinstance(r, Edge)]
        assert len(edges) == 2
        assert edges[0].type == RelationshipType.READS

    def test_no_false_positives(self, make_context):
        # Should NOT match arbitrary get calls
        text = 'requests.get("http://url")'
        extractor = SparkConfigExtractor()
        # It might pass can_extract if "spark" isn't in text, but extract should yield nothing
        results = list(extractor.extract(make_context(text)))
        assert len(results) == 0

class TestDeltaLakeExtractor:
    def test_extract_delta_paths(self, make_context):
        text = """
        dt = DeltaTable.forPath(spark, "s3://bucket/table")
        dt.alias("t").merge(
            source.alias("s"), "s.id = t.id"
        ).execute()
        """
        extractor = DeltaLakeExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        # Read from path
        read_node = next(n for n in results if isinstance(n, Node) and "bucket/table" in n.id)
        assert read_node.id == "data:delta:s3://bucket/table"
        assert read_node.metadata["format"] == "delta"
        
        # Read Edge
        read_edge = next(e for e in results if isinstance(e, Edge) and e.target_id == read_node.id)
        assert read_edge.type == RelationshipType.READS

    def test_extract_delta_name(self, make_context):
        text = 'DeltaTable.forName(spark, "schema.table_name")'
        extractor = DeltaLakeExtractor()
        results = list(extractor.extract(make_context(text)))
        
        node = results[0]
        assert node.id == "data:delta:schema.table_name"