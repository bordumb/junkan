"""Tests for SQLite Storage adapter enhancements."""

import json
import pytest
from pathlib import Path
from jnkn.core.storage.sqlite import SQLiteStorage
from jnkn.core.types import Node, NodeType


@pytest.fixture
def storage(tmp_path):
    db_path = tmp_path / "test.db"
    return SQLiteStorage(db_path)


def test_schema_migration_v4(storage):
    """Verify schema migration to version 4 (Multi-Repo Support)."""
    # Check if new tables exist
    with storage._connection() as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='token_index'"
        ).fetchone()
        assert tables is not None
        
        views = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='view' AND name='high_confidence_edges'"
        ).fetchone()
        assert views is not None

        # Check for V4 column: source_repo
        columns = conn.execute("PRAGMA table_info(nodes)").fetchall()
        column_names = [col[1] for col in columns]
        assert "source_repo" in column_names
        
    assert storage.get_schema_version() == 4


def test_batch_node_save_with_tokens_and_repo(storage):
    nodes = [
        Node(
            id="1", 
            name="A", 
            type=NodeType.CODE_FILE, 
            tokens=["t1", "common"],
            metadata={"source_repo": "app-repo"}
        ),
        Node(
            id="2", 
            name="B", 
            type=NodeType.ENV_VAR, 
            tokens=["t2", "common"],
            metadata={"source_repo": "infra-repo"}
        ),
    ]
    
    storage.save_nodes_batch(nodes)
    
    with storage._connection() as conn:
        # Check nodes count
        assert conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()["c"] == 2
        
        # Check source_repo persistence
        row_a = conn.execute("SELECT source_repo FROM nodes WHERE id='1'").fetchone()
        assert row_a["source_repo"] == "app-repo"

        # Check token index
        tokens = conn.execute("SELECT * FROM token_index ORDER BY token").fetchall()
        assert len(tokens) == 4 # t1, t2, common, common
        
        common_rows = conn.execute("SELECT node_id FROM token_index WHERE token='common'").fetchall()
        assert {row["node_id"] for row in common_rows} == {"1", "2"}


def test_high_confidence_view(storage):
    # This requires creating edges manually via SQL or extending test setup
    # to mock Edge insertion if save_edge is not fully exercised here.
    
    with storage._connection() as conn:
        conn.execute("""
            INSERT INTO edges (source_id, target_id, type, confidence, created_at)
            VALUES 
                ('a', 'b', 'reads', 0.9, '2023-01-01'),
                ('b', 'c', 'reads', 0.5, '2023-01-01')
        """)
        
        rows = conn.execute("SELECT * FROM high_confidence_edges").fetchall()
        assert len(rows) == 1
        assert rows[0]["confidence"] == 0.9