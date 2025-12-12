import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import rustworkx as rx

from jnkn.models import ImpactRelationship

DB_PATH = Path(".jnkn/jnkn.db")


class GraphStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        # Rustworkx uses integer indices for nodes
        self.graph = rx.PyDiGraph()
        # Map string IDs to integer indices
        self._id_to_idx: Dict[str, int] = {}
        # Map integer indices back to string IDs (for retrieval)
        self._idx_to_id: Dict[int, str] = {}

        self._init_db()
        self._load_from_db()

    def _init_db(self):
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        # Simple schema: distinct nodes and directed edges
        cur.execute("""
            CREATE TABLE IF NOT EXISTS edges (
                upstream TEXT,
                downstream TEXT,
                type TEXT,
                metadata JSON,
                PRIMARY KEY (upstream, downstream, type)
            )
        """)
        conn.commit()
        conn.close()

    def _load_from_db(self):
        """Hydrate Rustworkx graph from SQLite."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        try:
            rows = cur.execute("SELECT upstream, downstream, type, metadata FROM edges").fetchall()
            for u, d, t, m in rows:
                self._add_edge_to_memory(u, d, t, json.loads(m))
        except sqlite3.OperationalError:
            # Handle empty/new DB gracefully
            pass
        finally:
            conn.close()

    def _get_or_create_node(self, node_id: str) -> int:
        """Get existing node index or create new one."""
        if node_id in self._id_to_idx:
            return self._id_to_idx[node_id]

        idx = self.graph.add_node(node_id)
        self._id_to_idx[node_id] = idx
        self._idx_to_id[idx] = node_id
        return idx

    def _add_edge_to_memory(self, u: str, d: str, t: str, m: Dict[str, Any]):
        """Internal helper to add edge to rustworkx graph."""
        u_idx = self._get_or_create_node(u)
        d_idx = self._get_or_create_node(d)

        # Rustworkx allows multiple edges; check if exists to mimic NetworkX behavior if needed
        # For performance, we assume duplicate edges with same metadata are acceptable or handled by DB unique constraint
        self.graph.add_edge(u_idx, d_idx, {"relationship_type": t, "metadata": m})

    def add_relationship(self, rel: ImpactRelationship):
        """Write through to DB and update in-memory graph."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()

        # Upsert logic (SQLite specific)
        cur.execute(
            """
            INSERT OR REPLACE INTO edges (upstream, downstream, type, metadata)
            VALUES (?, ?, ?, ?)
        """,
            (
                rel.upstream_artifact,
                rel.downstream_artifact,
                rel.relationship_type,
                json.dumps(rel.metadata),
            ),
        )

        conn.commit()
        conn.close()

        self._add_edge_to_memory(
            rel.upstream_artifact, rel.downstream_artifact, rel.relationship_type, rel.metadata
        )

    def calculate_blast_radius(self, changed_artifacts: List[str]) -> Dict[str, Any]:
        """Core Impact Analysis Logic using Rustworkx."""
        unique_downstream = set()

        for root in changed_artifacts:
            if root in self._id_to_idx:
                root_idx = self._id_to_idx[root]
                # Rustworkx descendants returns indices
                descendant_indices = rx.descendants(self.graph, root_idx)
                unique_downstream.update(self._idx_to_id[i] for i in descendant_indices)

        # Categorize results
        breakdown = {"infra": [], "data": [], "code": [], "unknown": []}
        for art in unique_downstream:
            if any(x in art for x in ["aws_", "google_", "azure_", "k8s", "infra:"]):
                breakdown["infra"].append(art)
            elif any(x in art for x in ["table", "model", "view", "data:"]):
                breakdown["data"].append(art)
            elif art.endswith((".py", ".ts", ".js", ".go")) or "file:" in art:
                breakdown["code"].append(art)
            else:
                breakdown["unknown"].append(art)

        return {
            "source_artifacts": changed_artifacts,
            "total_impacted_count": len(unique_downstream),
            "impacted_artifacts": sorted(list(unique_downstream)),
            "breakdown": breakdown,
        }
