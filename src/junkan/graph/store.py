import sqlite3
import json
import networkx as nx
from pathlib import Path
from typing import List, Dict, Any
from junkan.models import ImpactRelationship

DB_PATH = Path(".junkan/junkan.db")

class GraphStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.graph = nx.DiGraph()
        self._init_db()
        self._load_from_db()

    def _init_db(self):
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True)
        
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
        """Hydrate NetworkX graph from SQLite."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        rows = cur.execute("SELECT upstream, downstream, type, metadata FROM edges").fetchall()
        for u, d, t, m in rows:
            self.graph.add_edge(u, d, relationship_type=t, metadata=json.loads(m))
        conn.close()

    def add_relationship(self, rel: ImpactRelationship):
        """Write through to DB and update in-memory graph."""
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        
        # Upsert logic (SQLite specific)
        cur.execute("""
            INSERT OR REPLACE INTO edges (upstream, downstream, type, metadata)
            VALUES (?, ?, ?, ?)
        """, (rel.upstream_artifact, rel.downstream_artifact, rel.relationship_type, json.dumps(rel.metadata)))
        
        conn.commit()
        conn.close()
        
        self.graph.add_edge(
            rel.upstream_artifact, 
            rel.downstream_artifact, 
            relationship_type=rel.relationship_type,
            metadata=rel.metadata
        )

    def calculate_blast_radius(self, changed_artifacts: List[str]) -> Dict[str, Any]:
        """Core Impact Analysis Logic."""
        unique_downstream = set()
        
        for root in changed_artifacts:
            if root in self.graph:
                descendants = nx.descendants(self.graph, root)
                unique_downstream.update(descendants)

        # Categorize results
        breakdown = {"infra": [], "data": [], "code": [], "unknown": []}
        for art in unique_downstream:
            if any(x in art for x in ["aws_", "google_", "azure_", "k8s"]):
                breakdown["infra"].append(art)
            elif any(x in art for x in ["table", "model", "view"]):
                breakdown["data"].append(art)
            elif art.endswith((".py", ".ts", ".js", ".go")):
                breakdown["code"].append(art)
            else:
                breakdown["unknown"].append(art)

        return {
            "source_artifacts": changed_artifacts,
            "total_impacted_count": len(unique_downstream),
            "impacted_artifacts": list(unique_downstream),
            "breakdown": breakdown
        }
