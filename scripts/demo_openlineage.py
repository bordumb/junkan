#!/usr/bin/env python3
"""
End-to-End Demo: Static Analysis + OpenLineage Integration

This demo shows how jnkn combines:
1. Static analysis (PySpark column lineage from code)
2. Runtime lineage (OpenLineage from production)

To create a complete pre-merge impact analysis system.

The key insight:
- Static analysis catches what WILL happen (predictive, pre-merge)
- Runtime lineage shows what DID happen (factual, post-execution)
- Together they provide complete coverage
"""

import json
from dataclasses import dataclass, field
from typing import Dict, List, Set, Any, Tuple
from collections import defaultdict

# Import our parsers
from jnkn.parsing.pyspark.column_lineage import extract_column_lineage, ColumnLineageExtractor, ColumnLineageResult
from jnkn.parsing.openlineage.parser import OpenLineageParser, Node, Edge, NodeType, RelationshipType


# =============================================================================
# Unified Graph
# =============================================================================

class UnifiedLineageGraph:
    """
    Combines static and runtime lineage into a unified graph.
    
    Key features:
    - Merges nodes from different sources
    - Tracks confidence levels (runtime=1.0, static=0.7-0.95)
    - Enables cross-source impact analysis
    """
    
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: List[Edge] = []
        self._outgoing: Dict[str, List[Edge]] = defaultdict(list)
        self._incoming: Dict[str, List[Edge]] = defaultdict(list)
    
    def add_node(self, node: Node, source: str = "unknown") -> None:
        """Add a node, merging if it already exists."""
        if node.id in self.nodes:
            # Merge metadata
            existing = self.nodes[node.id]
            existing.metadata.setdefault("sources", []).append(source)
        else:
            node.metadata.setdefault("sources", []).append(source)
            self.nodes[node.id] = node
    
    def add_edge(self, edge: Edge) -> None:
        """Add an edge."""
        self.edges.append(edge)
        self._outgoing[edge.source_id].append(edge)
        self._incoming[edge.target_id].append(edge)
    
    def get_downstream(self, node_id: str, max_depth: int = 10) -> List[Tuple[str, float, List[str]]]:
        """
        Get all downstream nodes with confidence and path.
        
        Returns:
            List of (node_id, min_confidence, path)
        """
        visited = set()
        results = []
        queue = [(node_id, 1.0, [node_id])]
        
        while queue:
            current, confidence, path = queue.pop(0)
            
            if current in visited or len(path) > max_depth:
                continue
            visited.add(current)
            
            if current != node_id:
                results.append((current, confidence, path))
            
            # Follow outgoing edges
            for edge in self._outgoing.get(current, []):
                if edge.type in (RelationshipType.WRITES, RelationshipType.TRANSFORMS):
                    new_conf = min(confidence, edge.confidence)
                    queue.append((edge.target_id, new_conf, path + [edge.target_id]))
            
            # Follow incoming READS edges (the reader is downstream of the data)
            for edge in self._incoming.get(current, []):
                if edge.type == RelationshipType.READS:
                    new_conf = min(confidence, edge.confidence)
                    queue.append((edge.source_id, new_conf, path + [edge.source_id]))
        
        return results
    
    def get_upstream(self, node_id: str, max_depth: int = 10) -> List[Tuple[str, float, List[str]]]:
        """Get all upstream nodes with confidence and path."""
        visited = set()
        results = []
        queue = [(node_id, 1.0, [node_id])]
        
        while queue:
            current, confidence, path = queue.pop(0)
            
            if current in visited or len(path) > max_depth:
                continue
            visited.add(current)
            
            if current != node_id:
                results.append((current, confidence, path))
            
            # Follow incoming WRITES edges
            for edge in self._incoming.get(current, []):
                if edge.type in (RelationshipType.WRITES, RelationshipType.TRANSFORMS):
                    new_conf = min(confidence, edge.confidence)
                    queue.append((edge.source_id, new_conf, path + [edge.source_id]))
            
            # Follow outgoing READS edges
            for edge in self._outgoing.get(current, []):
                if edge.type == RelationshipType.READS:
                    new_conf = min(confidence, edge.confidence)
                    queue.append((edge.target_id, new_conf, path + [edge.target_id]))
        
        return results
    
    def stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        sources = defaultdict(int)
        for node in self.nodes.values():
            for src in node.metadata.get("sources", ["unknown"]):
                sources[src] += 1
        
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "nodes_by_source": dict(sources),
            "node_types": dict(defaultdict(int, {
                n.type.value: sum(1 for x in self.nodes.values() if x.type == n.type)
                for n in self.nodes.values()
            })),
        }


# =============================================================================
# Demo Scenario
# =============================================================================

def create_demo_scenario():
    """
    Create a realistic demo scenario with both static and runtime data.
    
    Scenario:
    - A PySpark job (daily_user_etl.py) that processes user data
    - OpenLineage events from production showing actual execution
    - A proposed code change that modifies a column
    """
    
    # -------------------------------------------------------------------------
    # 1. STATIC ANALYSIS: Parse the PySpark code
    # -------------------------------------------------------------------------
    
    pyspark_code = '''
"""Daily User ETL Job - processes raw users into dim_users."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col, count, max as spark_max

spark = SparkSession.builder.appName("daily_user_etl").getOrCreate()

# Read from source tables
raw_users = spark.read.table("postgres.public.raw_users")
user_events = spark.read.table("postgres.public.user_events")

# Filter active users
active_users = raw_users.filter(col("status") == "active")

# Aggregate events per user
event_counts = user_events.groupBy("user_id").agg(
    count("event_id").alias("event_count"),
    spark_max("event_timestamp").alias("last_event_at")
)

# Join and create dim_users
dim_users = active_users.join(event_counts, "user_id", "left") \\
    .select(
        col("user_id"),
        col("email"),
        col("event_count"),
        col("last_event_at")
    )

# Write output
dim_users.write.mode("overwrite").saveAsTable("s3.warehouse.dim_users")
'''
    
    # -------------------------------------------------------------------------
    # 2. RUNTIME LINEAGE: OpenLineage events from production
    # -------------------------------------------------------------------------
    
    openlineage_events = [
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T10:00:00Z",
            "job": {"namespace": "spark", "name": "daily_user_etl"},
            "inputs": [
                {"namespace": "postgres", "name": "public.raw_users"},
                {"namespace": "postgres", "name": "public.user_events"}
            ],
            "outputs": [
                {"namespace": "s3", "name": "warehouse/dim_users"}
            ]
        },
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T11:00:00Z",
            "job": {"namespace": "spark", "name": "user_metrics_aggregator"},
            "inputs": [
                {"namespace": "s3", "name": "warehouse/dim_users"}
            ],
            "outputs": [
                {"namespace": "s3", "name": "warehouse/agg_user_metrics"}
            ]
        },
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T12:00:00Z",
            "job": {"namespace": "spark", "name": "executive_dashboard_loader"},
            "inputs": [
                {"namespace": "s3", "name": "warehouse/agg_user_metrics"}
            ],
            "outputs": [
                {"namespace": "redshift", "name": "analytics.exec_dashboard"}
            ]
        },
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T12:30:00Z",
            "job": {"namespace": "spark", "name": "churn_prediction_features"},
            "inputs": [
                {"namespace": "s3", "name": "warehouse/dim_users"}
            ],
            "outputs": [
                {"namespace": "s3", "name": "ml-features/churn_features"}
            ]
        }
    ]
    
    return pyspark_code, openlineage_events


def main():
    print("=" * 70)
    print("END-TO-END DEMO: Static Analysis + OpenLineage Integration")
    print("=" * 70)
    
    pyspark_code, openlineage_events = create_demo_scenario()
    
    # =========================================================================
    # Step 1: Extract static lineage from code
    # =========================================================================
    
    print("\n" + "─" * 70)
    print("STEP 1: Static Analysis (PySpark Code)")
    print("─" * 70)
    
    static_result = extract_column_lineage(pyspark_code, "daily_user_etl.py")
    
    print(f"\n📖 Columns Read: {len(static_result.columns_read)}")
    for col in static_result.columns_read:
        print(f"   {col.column:20} [{col.context.value:8}] confidence={col.confidence.label}")
    
    print(f"\n✏️  Columns Written: {len(static_result.columns_written)}")
    for col in static_result.columns_written:
        print(f"   {col.column:20} transform={col.transform or 'direct'}")
    
    # =========================================================================
    # Step 2: Parse OpenLineage events
    # =========================================================================
    
    print("\n" + "─" * 70)
    print("STEP 2: Runtime Lineage (OpenLineage)")
    print("─" * 70)
    
    ol_parser = OpenLineageParser()
    runtime_nodes = []
    runtime_edges = []
    
    for item in ol_parser.parse_events(openlineage_events):
        if isinstance(item, Node):
            runtime_nodes.append(item)
        elif isinstance(item, Edge):
            runtime_edges.append(item)
    
    print(f"\n📊 From {len(openlineage_events)} production events:")
    print(f"   Jobs discovered: {len([n for n in runtime_nodes if n.type == NodeType.JOB])}")
    print(f"   Datasets discovered: {len([n for n in runtime_nodes if n.type == NodeType.DATA_ASSET])}")
    print(f"   Relationships: {len(runtime_edges)}")
    
    print("\n   Jobs:")
    for node in runtime_nodes:
        if node.type == NodeType.JOB:
            print(f"      • {node.name}")
    
    print("\n   Datasets:")
    for node in runtime_nodes:
        if node.type == NodeType.DATA_ASSET and not node.id.startswith("column:"):
            print(f"      • {node.id.replace('data:', '')}")
    
    # =========================================================================
    # Step 3: Build unified graph
    # =========================================================================
    
    print("\n" + "─" * 70)
    print("STEP 3: Build Unified Graph")
    print("─" * 70)
    
    graph = UnifiedLineageGraph()
    
    # Add runtime nodes/edges (confidence=1.0)
    for node in runtime_nodes:
        graph.add_node(node, source="openlineage")
    for edge in runtime_edges:
        graph.add_edge(edge)
    
    # Add static analysis as code file node
    code_node = Node(
        id="file:daily_user_etl.py",
        name="daily_user_etl.py",
        type=NodeType.CODE_FILE,
        metadata={"columns_read": len(static_result.columns_read)}
    )
    graph.add_node(code_node, source="static")
    
    # Link code file to job (stitching!)
    graph.add_edge(Edge(
        source_id="file:daily_user_etl.py",
        target_id="job:spark/daily_user_etl",
        type=RelationshipType.PROVIDES,
        confidence=0.95,  # High confidence name match
        metadata={"match_type": "name_similarity"}
    ))
    
    stats = graph.stats()
    print(f"\n📈 Unified Graph Stats:")
    print(f"   Total nodes: {stats['total_nodes']}")
    print(f"   Total edges: {stats['total_edges']}")
    print(f"   Nodes by source: {stats['nodes_by_source']}")
    
    # =========================================================================
    # Step 4: Impact Analysis
    # =========================================================================
    
    print("\n" + "─" * 70)
    print("STEP 4: Impact Analysis")
    print("─" * 70)
    
    # Scenario: What if we change the dim_users table?
    target = "data:s3/warehouse/dim_users"
    
    print(f"\n🎯 Analyzing impact of changes to: {target}")
    
    downstream = graph.get_downstream(target)
    upstream = graph.get_upstream(target)
    
    print(f"\n⬆️  UPSTREAM ({len(upstream)} nodes):")
    for node_id, confidence, path in sorted(upstream, key=lambda x: -x[1]):
        print(f"   [{confidence:.0%}] {node_id}")
    
    print(f"\n⬇️  DOWNSTREAM ({len(downstream)} nodes) - WILL BE AFFECTED:")
    for node_id, confidence, path in sorted(downstream, key=lambda x: -x[1]):
        print(f"   [{confidence:.0%}] {node_id}")
        if len(path) > 2:
            print(f"            via: {' → '.join(path[1:-1])}")
    
    # =========================================================================
    # Step 5: Pre-Merge Check Simulation
    # =========================================================================
    
    print("\n" + "─" * 70)
    print("STEP 5: Pre-Merge Check (CI/CD Integration)")
    print("─" * 70)
    
    print("""
    Simulating: PR #1234 modifies daily_user_etl.py
    
    Changes detected:
    - Modified column: 'event_count' calculation
    - Added column: 'is_power_user' (new)
    - Removed column: 'last_event_at'
    """)
    
    # Simulate the check
    print("🔍 Running jnkn pre-merge check...")
    print()
    
    critical_tables = ["redshift/analytics.exec_dashboard"]
    ml_tables = ["s3/ml-features/churn_features"]
    
    affected_critical = [
        (node_id, conf) for node_id, conf, _ in downstream
        if any(t in node_id for t in critical_tables)
    ]
    
    affected_ml = [
        (node_id, conf) for node_id, conf, _ in downstream
        if any(t in node_id for t in ml_tables)
    ]
    
    if affected_critical:
        print("🚨 CRITICAL: This change affects executive dashboards!")
        for node_id, conf in affected_critical:
            print(f"   • {node_id} (confidence: {conf:.0%})")
        print()
    
    if affected_ml:
        print("⚠️  WARNING: This change affects ML feature pipelines!")
        for node_id, conf in affected_ml:
            print(f"   • {node_id} (confidence: {conf:.0%})")
        print()
    
    print("""
    ┌─────────────────────────────────────────────────────────────────────┐
    │                         PR CHECK RESULT                             │
    ├─────────────────────────────────────────────────────────────────────┤
    │                                                                     │
    │   ❌ BLOCKED - Requires approval from:                              │
    │      • @data-platform-team (critical dashboard impact)              │
    │      • @ml-engineering (feature pipeline impact)                    │
    │                                                                     │
    │   Downstream impact: 4 jobs, 2 critical systems                     │
    │   Confidence: 100% (based on OpenLineage production data)           │
    │                                                                     │
    │   Column changes:                                                   │
    │      - REMOVED: last_event_at → breaks churn_features               │
    │      - MODIFIED: event_count → may affect exec_dashboard            │
    │                                                                     │
    └─────────────────────────────────────────────────────────────────────┘
    """)
    
    # =========================================================================
    # Summary
    # =========================================================================
    
    print("=" * 70)
    print("SUMMARY: Why This Matters")
    print("=" * 70)
    print("""
    WITHOUT jnkn + OpenLineage:
    ─────────────────────────────
    1. Developer changes event_count calculation
    2. PR passes tests (unit tests don't check downstream)
    3. Merges to main, deploys
    4. Executive dashboard shows wrong numbers
    5. ML model accuracy drops
    6. On-call gets paged at 3am
    7. 4 hours to debug the root cause
    
    WITH jnkn + OpenLineage:
    ──────────────────────────
    1. Developer changes event_count calculation
    2. jnkn runs on PR:
       - Static analysis: sees column modification
       - OpenLineage lookup: finds downstream consumers
       - Combined: identifies executive dashboard + ML impact
    3. PR blocked, notifies data platform + ML teams
    4. Developer adds migration plan
    5. Coordinated rollout with downstream teams
    6. No 3am pages, no data incidents
    
    KEY INSIGHT:
    ─────────────
    Static analysis alone can't know that exec_dashboard depends on dim_users.
    That information only exists in production execution history.
    
    OpenLineage alone can't predict what a PR will change.
    That requires parsing the code diff.
    
    Together, they provide complete pre-merge impact analysis.
    """)


if __name__ == "__main__":
    main()