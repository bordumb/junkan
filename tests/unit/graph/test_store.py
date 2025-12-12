"""
Unit tests for the GraphStore (Rustworkx + SQLite backend).
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from jnkn.graph.store import GraphStore
from jnkn.models import ImpactRelationship, RelationshipType

class TestGraphStore:
    
    @pytest.fixture
    def db_path(self, tmp_path):
        """Provide a temporary path for the SQLite DB."""
        return tmp_path / ".jnkn" / "jnkn.db"

    def test_init_creates_db_schema(self, db_path):
        """Test that initialization creates the DB directory and table."""
        store = GraphStore(db_path)
        
        assert db_path.exists()
        
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Verify table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='edges'")
        assert cursor.fetchone() is not None
        
        conn.close()

    def test_add_relationship_persists_to_db_and_memory(self, db_path):
        """Test adding a relationship updates both SQLite and Rustworkx."""
        store = GraphStore(db_path)
        
        rel = ImpactRelationship(
            upstream_artifact="infra:aws_s3.bucket",
            downstream_artifact="env:BUCKET_NAME",
            relationship_type=RelationshipType.PROVIDES,
            metadata={"source": "terraform"}
        )
        
        store.add_relationship(rel)
        
        # 1. Verify Memory (Rustworkx)
        # Check node existence via ID mapping
        assert "infra:aws_s3.bucket" in store._id_to_idx
        assert "env:BUCKET_NAME" in store._id_to_idx
        
        u_idx = store._id_to_idx["infra:aws_s3.bucket"]
        d_idx = store._id_to_idx["env:BUCKET_NAME"]
        
        # Check edge existence
        assert store.graph.has_edge(u_idx, d_idx)
        
        # Check edge data
        edge_data = store.graph.get_edge_data(u_idx, d_idx)
        assert edge_data["relationship_type"] == RelationshipType.PROVIDES
        assert edge_data["metadata"] == {"source": "terraform"}
        
        # 2. Verify Persistence (SQLite)
        # Create new store instance to force reload from DB
        store2 = GraphStore(db_path)
        assert "infra:aws_s3.bucket" in store2._id_to_idx
        u2 = store2._id_to_idx["infra:aws_s3.bucket"]
        d2 = store2._id_to_idx["env:BUCKET_NAME"]
        assert store2.graph.has_edge(u2, d2)

    def test_load_from_db(self, db_path):
        """Test hydration from existing DB."""
        # Manually populate DB
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE edges (upstream TEXT, downstream TEXT, type TEXT, metadata JSON, PRIMARY KEY (upstream, downstream, type))
        """)
        cursor.execute(
            "INSERT INTO edges VALUES (?, ?, ?, ?)",
            ("A", "B", "reads", '{"test": true}')
        )
        conn.commit()
        conn.close()
        
        store = GraphStore(db_path)
        
        assert "A" in store._id_to_idx
        assert "B" in store._id_to_idx
        
        u = store._id_to_idx["A"]
        v = store._id_to_idx["B"]
        
        assert store.graph.has_edge(u, v)
        edge_data = store.graph.get_edge_data(u, v)
        assert edge_data["metadata"]["test"] is True

    def test_calculate_blast_radius_traversal(self, db_path):
        """Test recursive traversal for blast radius."""
        store = GraphStore(db_path)
        
        # A -> B -> C
        store._add_edge_to_memory("A", "B", "rel", {})
        store._add_edge_to_memory("B", "C", "rel", {})
        
        # D (disconnected)
        store._get_or_create_node("D")
        
        result = store.calculate_blast_radius(["A"])
        
        assert result["total_impacted_count"] == 2
        assert "B" in result["impacted_artifacts"]
        assert "C" in result["impacted_artifacts"]
        assert "D" not in result["impacted_artifacts"]

    def test_calculate_blast_radius_breakdown(self, db_path):
        """Test categorization logic in blast radius breakdown."""
        store = GraphStore(db_path)
        
        # Setup specific naming patterns to trigger breakdown categories
        nodes = [
            "root",
            "infra:aws_db_instance",  # Should trigger 'infra'
            "data:table.users",       # Should trigger 'data'
            "src/main.py",            # Should trigger 'code'
            "unknown_artifact"        # Should trigger 'unknown'
        ]
        
        for node in nodes[1:]:
            store._add_edge_to_memory("root", node, "rel", {})
            
        result = store.calculate_blast_radius(["root"])
        breakdown = result["breakdown"]
        
        assert "infra:aws_db_instance" in breakdown["infra"]
        assert "data:table.users" in breakdown["data"]
        assert "src/main.py" in breakdown["code"]
        assert "unknown_artifact" in breakdown["unknown"]

    def test_blast_radius_missing_node(self, db_path):
        """Test behavior when source node is not in graph."""
        store = GraphStore(db_path)
        result = store.calculate_blast_radius(["GHOST"])
        
        assert result["total_impacted_count"] == 0
        assert result["impacted_artifacts"] == []