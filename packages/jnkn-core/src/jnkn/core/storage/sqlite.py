"""
SQLite storage adapter with schema v3 enhancements.

New capabilities:
- Persisted Token Index to speed up graph hydration
- High-confidence view for filtered analysis
- Batch operations for token index
"""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..graph import DependencyGraph
from ..types import Edge, MatchStrategy, Node, NodeType, RelationshipType, ScanMetadata
from .base import StorageAdapter

# Bump schema version to support source_repo column
SCHEMA_VERSION = 4


class SQLiteStorage(StorageAdapter):
    """
    Persistent storage using local SQLite file.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connection(self):
        """Context manager for database connections with WAL mode."""
        conn = sqlite3.connect(
            self.db_path, detect_types=sqlite3.PARSE_DECLTYPES | sqlite3.PARSE_COLNAMES
        )
        conn.row_factory = sqlite3.Row
        # Performance tuning for bulk writes
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
        row = conn.execute("SELECT MAX(version) as v FROM schema_version").fetchone()
        return row["v"] if row and row["v"] else 0

    def _migrate(self, conn: sqlite3.Connection, from_version: int) -> None:
        """Run schema migrations."""

        # V1: Base Schema
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

            conn.execute(
                """
                INSERT INTO schema_version (version, applied_at, description)
                VALUES (1, ?, 'Initial schema')
            """,
                (datetime.now(timezone.utc).isoformat(),),
            )

        # V2: Confidence Index
        if from_version < 2:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(confidence)")
            conn.execute(
                """
                INSERT INTO schema_version (version, applied_at, description)
                VALUES (2, ?, 'Added confidence index')
            """,
                (datetime.now(timezone.utc).isoformat(),),
            )

        # V3: Token Index and High-Confidence View
        if from_version < 3:
            # Token Index Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS token_index (
                    token TEXT NOT NULL,
                    node_id TEXT NOT NULL,
                    PRIMARY KEY (token, node_id),
                    FOREIGN KEY (node_id) REFERENCES nodes(id) ON DELETE CASCADE
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_token_lookup ON token_index(token)")

            # High Confidence View (Pruning optimization)
            conn.execute("""
                CREATE VIEW IF NOT EXISTS high_confidence_edges AS
                SELECT * FROM edges WHERE confidence >= 0.7
            """)

            conn.execute(
                """
                INSERT INTO schema_version (version, applied_at, description)
                VALUES (3, ?, 'Added token_index table and high_confidence_edges view')
            """,
                (datetime.now(timezone.utc).isoformat(),),
            )

        # V4: Multi-Repo support (Source Repo tracking)
        if from_version < 4:
            # Add source_repo column to nodes
            try:
                conn.execute("ALTER TABLE nodes ADD COLUMN source_repo TEXT")
            except sqlite3.OperationalError:
                # Column might already exist if re-running migration on dev env
                pass

            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_source_repo ON nodes(source_repo)")

            conn.execute(
                """
                INSERT INTO schema_version (version, applied_at, description)
                VALUES (4, ?, 'Added source_repo column to nodes table')
            """,
                (datetime.now(timezone.utc).isoformat(),),
            )

    def get_schema_version(self) -> int:
        with self._connection() as conn:
            return self._get_schema_version_internal(conn)

    # --- Node Persistence ---

    def save_node(self, node: Node) -> None:
        """Persist a single node."""
        self.save_nodes_batch([node])

    def save_nodes_batch(self, nodes: List[Node]) -> int:
        """Persist multiple nodes and their tokens in a single transaction."""
        if not nodes:
            return 0

        with self._connection() as conn:
            # 1. Upsert Nodes
            # Ensure we handle source_repo from metadata
            conn.executemany(
                """
                INSERT OR REPLACE INTO nodes 
                (id, name, type, path, language, file_hash, tokens, metadata, created_at, source_repo)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        n.id,
                        n.name,
                        n.type.value,
                        n.path,
                        n.language,
                        n.file_hash,
                        json.dumps(n.tokens),
                        json.dumps(n.metadata),
                        n.created_at.isoformat(),
                        n.metadata.get("source_repo"),  # Extract source_repo from metadata
                    )
                    for n in nodes
                ],
            )

            # 2. Update Token Index
            # Delete existing tokens for these nodes first to ensure clean state on update
            node_ids = [n.id for n in nodes]
            placeholders = ",".join("?" * len(node_ids))
            conn.execute(f"DELETE FROM token_index WHERE node_id IN ({placeholders})", node_ids)

            # Flatten tokens for batch insert
            token_entries = []
            for node in nodes:
                # Use tokens from the object, defaulting to computed ones if missing
                tokens = node.tokens or []
                for token in tokens:
                    token_entries.append((token, node.id))

            if token_entries:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO token_index (token, node_id)
                    VALUES (?, ?)
                """,
                    token_entries,
                )

        return len(nodes)

    def load_node(self, node_id: str) -> Node | None:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
            return self._row_to_node(row) if row else None

    def load_all_nodes(self) -> List[Node]:
        nodes = []
        with self._connection() as conn:
            for row in conn.execute("SELECT * FROM nodes").fetchall():
                nodes.append(self._row_to_node(row))
        return nodes

    def _row_to_node(self, row: sqlite3.Row) -> Node:
        metadata = json.loads(row["metadata"]) if row["metadata"] else {}
        # Inject source_repo back into metadata if present in column but not json
        if "source_repo" in row.keys() and row["source_repo"] and "source_repo" not in metadata:
            metadata["source_repo"] = row["source_repo"]

        return Node(
            id=row["id"],
            name=row["name"],
            type=NodeType(row["type"]),
            path=row["path"],
            language=row["language"],
            file_hash=row["file_hash"],
            tokens=json.loads(row["tokens"]) if row["tokens"] else [],
            metadata=metadata,
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def delete_node(self, node_id: str) -> bool:
        with self._connection() as conn:
            # Cascading delete handles token_index via FK
            conn.execute(
                "DELETE FROM edges WHERE source_id = ? OR target_id = ?", (node_id, node_id)
            )
            cursor = conn.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            return cursor.rowcount > 0

    def delete_nodes_by_file(self, file_path: str) -> int:
        with self._connection() as conn:
            # Find IDs
            rows = conn.execute("SELECT id FROM nodes WHERE path = ?", (file_path,)).fetchall()
            node_ids = [row["id"] for row in rows]

            if not node_ids:
                return 0

            placeholders = ",".join("?" * len(node_ids))

            # Delete Edges
            conn.execute(
                f"""
                DELETE FROM edges 
                WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})
            """,
                node_ids + node_ids,
            )

            # Delete Nodes (Cascades to token_index)
            cursor = conn.execute(f"DELETE FROM nodes WHERE id IN ({placeholders})", node_ids)
            return cursor.rowcount

    # --- Edge Persistence ---

    def save_edge(self, edge: Edge) -> None:
        self.save_edges_batch([edge])

    def save_edges_batch(self, edges: List[Edge]) -> int:
        if not edges:
            return 0

        with self._connection() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO edges 
                (source_id, target_id, type, confidence, match_strategy, metadata, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                [
                    (
                        e.source_id,
                        e.target_id,
                        e.type.value,
                        e.confidence,
                        e.match_strategy.value if e.match_strategy else None,
                        json.dumps(e.metadata),
                        e.created_at.isoformat(),
                    )
                    for e in edges
                ],
            )
        return len(edges)

    def load_all_edges(self, min_confidence: float = 0.0) -> List[Edge]:
        """
        Load all edges, optionally filtering by confidence.
        Uses the high_confidence_edges view if threshold >= 0.7.
        """
        table = "high_confidence_edges" if min_confidence >= 0.7 else "edges"
        query = f"SELECT * FROM {table}"
        params = []

        if 0.0 < min_confidence < 0.7:
            query += " WHERE confidence >= ?"
            params.append(min_confidence)

        edges = []
        with self._connection() as conn:
            for row in conn.execute(query, params).fetchall():
                try:
                    edges.append(self._row_to_edge(row))
                except Exception:
                    pass
        return edges

    def _row_to_edge(self, row: sqlite3.Row) -> Edge:
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
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM edges WHERE source_id = ?", (source_id,))
            return cursor.rowcount

    # --- Scan Metadata Persistence ---

    def save_scan_metadata(self, metadata: ScanMetadata) -> None:
        with self._connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scan_metadata 
                (file_path, file_hash, last_scanned, node_count, edge_count)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    metadata.file_path,
                    metadata.file_hash,
                    metadata.last_scanned.isoformat(),
                    metadata.node_count,
                    metadata.edge_count,
                ),
            )

    def get_scan_metadata(self, file_path: str) -> ScanMetadata | None:
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
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM scan_metadata WHERE file_path = ?", (file_path,))
            return cursor.rowcount > 0

    # --- Graph Hydration ---

    def load_graph(self) -> DependencyGraph:
        """
        Hydrate a full DependencyGraph from storage.

        Optimized to load token index from DB rather than rebuilding it.
        """
        graph = DependencyGraph()

        # Load nodes
        all_nodes = self.load_all_nodes()
        for node in all_nodes:
            graph.add_node(node)

        # Load edges
        all_edges = self.load_all_edges()
        for edge in all_edges:
            graph.add_edge(edge)

        return graph

    # --- Traversal Queries ---

    def query_descendants(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query all descendants using recursive CTE."""
        with self._connection() as conn:
            if max_depth < 0:
                rows = conn.execute(
                    """
                    WITH RECURSIVE descendants AS (
                        SELECT target_id as id, 1 as depth
                        FROM edges WHERE source_id = ?
                        UNION
                        SELECT e.target_id, d.depth + 1
                        FROM edges e JOIN descendants d ON e.source_id = d.id
                    )
                    SELECT DISTINCT id FROM descendants
                """,
                    (node_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    WITH RECURSIVE descendants AS (
                        SELECT target_id as id, 1 as depth
                        FROM edges WHERE source_id = ?
                        UNION
                        SELECT e.target_id, d.depth + 1
                        FROM edges e JOIN descendants d ON e.source_id = d.id
                        WHERE d.depth < ?
                    )
                    SELECT DISTINCT id FROM descendants
                """,
                    (node_id, max_depth),
                ).fetchall()
            return [row["id"] for row in rows]

    def query_ancestors(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query all ancestors using recursive CTE."""
        with self._connection() as conn:
            if max_depth < 0:
                rows = conn.execute(
                    """
                    WITH RECURSIVE ancestors AS (
                        SELECT source_id as id, 1 as depth
                        FROM edges WHERE target_id = ?
                        UNION
                        SELECT e.source_id, a.depth + 1
                        FROM edges e JOIN ancestors a ON e.target_id = a.id
                    )
                    SELECT DISTINCT id FROM ancestors
                """,
                    (node_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    WITH RECURSIVE ancestors AS (
                        SELECT source_id as id, 1 as depth
                        FROM edges WHERE target_id = ?
                        UNION
                        SELECT e.source_id, a.depth + 1
                        FROM edges e JOIN ancestors a ON e.target_id = a.id
                        WHERE a.depth < ?
                    )
                    SELECT DISTINCT id FROM ancestors
                """,
                    (node_id, max_depth),
                ).fetchall()
            return [row["id"] for row in rows]

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        with self._connection() as conn:
            node_count = conn.execute("SELECT COUNT(*) as c FROM nodes").fetchone()["c"]
            edge_count = conn.execute("SELECT COUNT(*) as c FROM edges").fetchone()["c"]
            file_count = conn.execute("SELECT COUNT(*) as c FROM scan_metadata").fetchone()["c"]
            token_count = conn.execute("SELECT COUNT(*) as c FROM token_index").fetchone()["c"]

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
                "indexed_tokens": token_count,
                "nodes_by_type": {row["type"]: row["c"] for row in type_rows},
                "edges_by_type": {row["type"]: row["c"] for row in edge_type_rows},
                "db_size_bytes": self.db_path.stat().st_size if self.db_path.exists() else 0,
            }

    def clear(self) -> None:
        """Clear all data."""
        with self._connection() as conn:
            conn.execute("DELETE FROM edges")
            conn.execute("DELETE FROM token_index")  # Explicit, though cascade handles it
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM scan_metadata")

    def close(self) -> None:
        """Close connections if needed."""
        pass
