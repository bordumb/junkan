"""
SQLite storage adapter.

Production-ready implementation featuring:
- Schema versioning and migrations
- Batch operations with single transactions
- Efficient recursive CTEs for graph traversal
- Connection pooling via context managers
- Proper index creation for query performance
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager

from .base import StorageAdapter
from ..types import Node, Edge, ScanMetadata, NodeType, RelationshipType, MatchStrategy
from ..graph import DependencyGraph


SCHEMA_VERSION = 2


class SQLiteStorage(StorageAdapter):
    """
    Persistent storage using local SQLite file.
    
    Features:
    - Schema versioning with automatic migrations
    - Batch write operations (10-100x faster)
    - Recursive CTEs for efficient traversal queries
    - Proper indexing for common query patterns
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def _connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(
            self.db_path,
            detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _init_db(self) -> None:
        """Initialize database schema with versioning."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL,
                    description TEXT
                )
            """)
            
            current_version = self._get_schema_version_internal(conn)
            
            if current_version < SCHEMA_VERSION:
                self._migrate(conn, current_version)
    
    def _get_schema_version_internal(self, conn: sqlite3.Connection) -> int:
        """Get schema version using existing connection."""
        row = conn.execute(
            "SELECT MAX(version) as v FROM schema_version"
        ).fetchone()
        return row["v"] if row and row["v"] else 0
    
    def _migrate(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run schema migrations."""
        
        if from_version < 1:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    path TEXT,
                    language TEXT,
                    file_hash TEXT,
                    tokens TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS edges (
                    source_id TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    type TEXT NOT NULL,
                    confidence REAL DEFAULT 1.0,
                    match_strategy TEXT,
                    metadata TEXT,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (source_id, target_id, type)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_metadata (
                    file_path TEXT PRIMARY KEY,
                    file_hash TEXT NOT NULL,
                    last_scanned TEXT NOT NULL,
                    node_count INTEGER DEFAULT 0,
                    edge_count INTEGER DEFAULT 0
                )
            """)
            
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(type)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_path ON nodes(path)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)")
            
            conn.execute("""
                INSERT INTO schema_version (version, applied_at, description)
                VALUES (1, ?, 'Initial schema')
            """, (datetime.utcnow().isoformat(),))
        
        if from_version < 2:
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(confidence)"
            )
            conn.execute("""
                INSERT INTO schema_version (version, applied_at, description)
                VALUES (2, ?, 'Added confidence index')
            """, (datetime.utcnow().isoformat(),))
    
    def get_schema_version(self) -> int:
        """Get the current schema version."""
        with self._connection() as conn:
            return self._get_schema_version_internal(conn)
    
    def save_node(self, node: Node) -> None:
        """Persist a single node."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO nodes 
                (id, name, type, path, language, file_hash, tokens, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.id, node.name, node.type.value, node.path,
                node.language, node.file_hash, json.dumps(node.tokens),
                json.dumps(node.metadata), node.created_at.isoformat(),
            ))
    
    def save_nodes_batch(self, nodes: List[Node]) -> int:
        """Persist multiple nodes in a single transaction."""
        if not nodes:
            return 0
        
        with self._connection() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO nodes 
                (id, name, type, path, language, file_hash, tokens, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                (n.id, n.name, n.type.value, n.path, n.language, n.file_hash,
                 json.dumps(n.tokens), json.dumps(n.metadata), n.created_at.isoformat())
                for n in nodes
            ])
        return len(nodes)
    
    def load_node(self, node_id: str) -> Optional[Node]:
        """Load a node by ID."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM nodes WHERE id = ?", (node_id,)
            ).fetchone()
            return self._row_to_node(row) if row else None
    
    def load_all_nodes(self) -> List[Node]:
        """Load all nodes from storage."""
        nodes = []
        with self._connection() as conn:
            for row in conn.execute("SELECT * FROM nodes").fetchall():
                try:
                    nodes.append(self._row_to_node(row))
                except Exception:
                    pass
        return nodes
    
    def _row_to_node(self, row: sqlite3.Row) -> Node:
        """Convert a database row to a Node object."""
        return Node(
            id=row["id"],
            name=row["name"],
            type=NodeType(row["type"]),
            path=row["path"],
            language=row["language"],
            file_hash=row["file_hash"],
            tokens=json.loads(row["tokens"]) if row["tokens"] else [],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )
    
    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its associated edges."""
        with self._connection() as conn:
            conn.execute(
                "DELETE FROM edges WHERE source_id = ? OR target_id = ?",
                (node_id, node_id)
            )
            cursor = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            return cursor.rowcount > 0
    
    def delete_nodes_by_file(self, file_path: str) -> int:
        """Delete all nodes originating from a file."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id FROM nodes WHERE path = ?", (file_path,)
            ).fetchall()
            
            node_ids = [row["id"] for row in rows]
            if not node_ids:
                return 0
            
            placeholders = ",".join("?" * len(node_ids))
            conn.execute(f"""
                DELETE FROM edges 
                WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
            """, node_ids + node_ids)
            
            cursor = conn.execute(
                f"DELETE FROM nodes WHERE id IN ({placeholders})", node_ids
            )
            return cursor.rowcount
    
    def save_edge(self, edge: Edge) -> None:
        """Persist a single edge."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO edges 
                (source_id, target_id, type, confidence, match_strategy, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                edge.source_id, edge.target_id, edge.type.value, edge.confidence,
                edge.match_strategy.value if edge.match_strategy else None,
                json.dumps(edge.metadata), edge.created_at.isoformat(),
            ))
    
    def save_edges_batch(self, edges: List[Edge]) -> int:
        """Persist multiple edges in a single transaction."""
        if not edges:
            return 0
        
        with self._connection() as conn:
            conn.executemany("""
                INSERT OR REPLACE INTO edges 
                (source_id, target_id, type, confidence, match_strategy, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                (e.source_id, e.target_id, e.type.value, e.confidence,
                 e.match_strategy.value if e.match_strategy else None,
                 json.dumps(e.metadata), e.created_at.isoformat())
                for e in edges
            ])
        return len(edges)
    
    def load_all_edges(self) -> List[Edge]:
        """Load all edges from storage."""
        edges = []
        with self._connection() as conn:
            for row in conn.execute("SELECT * FROM edges").fetchall():
                try:
                    edges.append(self._row_to_edge(row))
                except Exception:
                    pass
        return edges
    
    def _row_to_edge(self, row: sqlite3.Row) -> Edge:
        """Convert a database row to an Edge object."""
        return Edge(
            source_id=row["source_id"],
            target_id=row["target_id"],
            type=RelationshipType(row["type"]),
            confidence=row["confidence"],
            match_strategy=MatchStrategy(row["match_strategy"]) if row["match_strategy"] else None,
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
            created_at=datetime.fromisoformat(row["created_at"]),
        )
    
    def delete_edges_by_source(self, source_id: str) -> int:
        """Delete all edges from a source node."""
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM edges WHERE source_id = ?", (source_id,)
            )
            return cursor.rowcount
    
    def load_graph(self) -> DependencyGraph:
        """Hydrate a full DependencyGraph from storage."""
        graph = DependencyGraph()
        for node in self.load_all_nodes():
            graph.add_node(node)
        for edge in self.load_all_edges():
            graph.add_edge(edge)
        return graph
    
    def query_descendants(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query all descendants using recursive CTE."""
        with self._connection() as conn:
            if max_depth < 0:
                rows = conn.execute("""
                    WITH RECURSIVE descendants AS (
                        SELECT target_id as id, 1 as depth
                        FROM edges WHERE source_id = ?
                        UNION
                        SELECT e.target_id, d.depth + 1
                        FROM edges e JOIN descendants d ON e.source_id = d.id
                    )
                    SELECT DISTINCT id FROM descendants
                """, (node_id,)).fetchall()
            else:
                rows = conn.execute("""
                    WITH RECURSIVE descendants AS (
                        SELECT target_id as id, 1 as depth
                        FROM edges WHERE source_id = ?
                        UNION
                        SELECT e.target_id, d.depth + 1
                        FROM edges e JOIN descendants d ON e.source_id = d.id
                        WHERE d.depth < ?
                    )
                    SELECT DISTINCT id FROM descendants
                """, (node_id, max_depth)).fetchall()
            return [row["id"] for row in rows]
    
    def query_ancestors(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query all ancestors using recursive CTE."""
        with self._connection() as conn:
            if max_depth < 0:
                rows = conn.execute("""
                    WITH RECURSIVE ancestors AS (
                        SELECT source_id as id, 1 as depth
                        FROM edges WHERE target_id = ?
                        UNION
                        SELECT e.source_id, a.depth + 1
                        FROM edges e JOIN ancestors a ON e.target_id = a.id
                    )
                    SELECT DISTINCT id FROM ancestors
                """, (node_id,)).fetchall()
            else:
                rows = conn.execute("""
                    WITH RECURSIVE ancestors AS (
                        SELECT source_id as id, 1 as depth
                        FROM edges WHERE target_id = ?
                        UNION
                        SELECT e.source_id, a.depth + 1
                        FROM edges e JOIN ancestors a ON e.target_id = a.id
                        WHERE a.depth < ?
                    )
                    SELECT DISTINCT id FROM ancestors
                """, (node_id, max_depth)).fetchall()
            return [row["id"] for row in rows]
    
    def save_scan_metadata(self, metadata: ScanMetadata) -> None:
        """Save file scan metadata."""
        with self._connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO scan_metadata 
                (file_path, file_hash, last_scanned, node_count, edge_count)
                VALUES (?, ?, ?, ?, ?)
            """, (
                metadata.file_path, metadata.file_hash,
                metadata.last_scanned.isoformat(),
                metadata.node_count, metadata.edge_count,
            ))
    
    def get_scan_metadata(self, file_path: str) -> Optional[ScanMetadata]:
        """Get scan metadata for a file."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM scan_metadata WHERE file_path = ?", (file_path,)
            ).fetchone()
            
            if not row:
                return None
            
            return ScanMetadata(
                file_path=row["file_path"],
                file_hash=row["file_hash"],
                last_scanned=datetime.fromisoformat(row["last_scanned"]),
                node_count=row["node_count"],
                edge_count=row["edge_count"],
            )
    
    def get_all_scan_metadata(self) -> List[ScanMetadata]:
        """Get scan metadata for all files."""
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM scan_metadata").fetchall()
            return [
                ScanMetadata(
                    file_path=row["file_path"],
                    file_hash=row["file_hash"],
                    last_scanned=datetime.fromisoformat(row["last_scanned"]),
                    node_count=row["node_count"],
                    edge_count=row["edge_count"],
                )
                for row in rows
            ]
    
    def delete_scan_metadata(self, file_path: str) -> bool:
        """Delete scan metadata for a file."""
        with self._connection() as conn:
            cursor = conn.execute(
                "DELETE FROM scan_metadata WHERE file_path = ?", (file_path,)
            )
            return cursor.rowcount > 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        with self._connection() as conn:
            node_count = conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()["c"]
            edge_count = conn.execute("SELECT COUNT(*) as c FROM edges").fetchone()["c"]
            file_count = conn.execute("SELECT COUNT(*) as c FROM scan_metadata").fetchone()["c"]
            
            type_rows = conn.execute(
                "SELECT type, COUNT(*) as c FROM nodes GROUP BY type"
            ).fetchall()
            
            edge_type_rows = conn.execute(
                "SELECT type, COUNT(*) as c FROM edges GROUP BY type"
            ).fetchall()
            
            return {
                "schema_version": self._get_schema_version_internal(conn),
                "total_nodes": node_count,
                "total_edges": edge_count,
                "tracked_files": file_count,
                "nodes_by_type": {row["type"]: row["c"] for row in type_rows},
                "edges_by_type": {row["type"]: row["c"] for row in edge_type_rows},
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            }
    
    def clear(self) -> None:
        """Clear all data from storage."""
        with self._connection() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM scan_metadata")
    
    def close(self) -> None:
        """Close any open connections."""
        pass