#!/usr/bin/env python3
"""
jnkn CLI Demo - Complete Working Example

This script demonstrates the full workflow:
1. Creates a sample data pipeline (PySpark jobs + config)
2. Scans files to build lineage graph
3. Runs impact analysis
4. Generates interactive visualization

Run with:
    python demo_cli_example.py
    
Then open lineage.html in your browser!
"""

import json
import tempfile
import shutil
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Set, Tuple

# =============================================================================
# Sample Data Pipeline Files
# =============================================================================

SAMPLE_FILES = {
    # ---------------------------------------------------------------------
    # Job 1: Ingest raw events from Kafka
    # ---------------------------------------------------------------------
    "jobs/ingest_events.py": '''"""Ingest raw events from Kafka to staging."""
import os
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("IngestEvents").getOrCreate()

# Read from Kafka source
raw_events = spark.read.table("kafka.raw_events")

# Write to staging area
raw_events.write \\
    .format("delta") \\
    .mode("append") \\
    .save("s3://data-lake/staging/events/")
''',

    # ---------------------------------------------------------------------
    # Job 2: Process and join with dimensions
    # ---------------------------------------------------------------------
    "jobs/process_events.py": '''"""Process events and join with user dimensions."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("ProcessEvents").getOrCreate()

# Read staging data
staging_events = spark.read.format("delta").load("s3://data-lake/staging/events/")

# Read dimension table
dim_users = spark.read.table("warehouse.dim_users")

# Join and enrich
processed = staging_events \\
    .join(dim_users, "user_id", "left") \\
    .filter(F.col("event_type").isNotNull())

# Write to warehouse
processed.write \\
    .mode("overwrite") \\
    .saveAsTable("warehouse.fact_events")
''',

    # ---------------------------------------------------------------------
    # Job 3: Build daily aggregates
    # ---------------------------------------------------------------------
    "jobs/daily_aggregates.py": '''"""Build daily aggregate metrics."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.appName("DailyAggregates").getOrCreate()

# Read fact table
fact_events = spark.read.table("warehouse.fact_events")

# Read dimensions
dim_users = spark.read.table("warehouse.dim_users")

# Calculate daily metrics
daily = fact_events.groupBy(
    F.to_date("event_timestamp").alias("date"),
    "user_id"
).agg(
    F.count("*").alias("event_count"),
    F.sum("revenue").alias("total_revenue")
)

# Join with user segments
enriched = daily.join(dim_users.select("user_id", "segment"), "user_id")

# Write to warehouse
enriched.write.mode("overwrite").saveAsTable("warehouse.daily_metrics")

# Write to reporting layer
summary = enriched.groupBy("date", "segment").agg(
    F.sum("event_count").alias("events"),
    F.sum("total_revenue").alias("revenue")
)
summary.write.mode("overwrite").saveAsTable("reporting.daily_summary")
''',

    # ---------------------------------------------------------------------
    # Job 4: ML feature engineering
    # ---------------------------------------------------------------------
    "jobs/ml_features.py": '''"""Generate ML features from metrics."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.window import Window

spark = SparkSession.builder.appName("MLFeatures").getOrCreate()

# Read source tables
daily_metrics = spark.read.table("warehouse.daily_metrics")
fact_events = spark.read.table("warehouse.fact_events")

# Calculate rolling windows
window_7d = Window.partitionBy("user_id").orderBy("date").rowsBetween(-6, 0)
window_30d = Window.partitionBy("user_id").orderBy("date").rowsBetween(-29, 0)

features = daily_metrics \\
    .withColumn("events_7d", F.sum("event_count").over(window_7d)) \\
    .withColumn("events_30d", F.sum("event_count").over(window_30d)) \\
    .withColumn("revenue_7d", F.sum("total_revenue").over(window_7d))

# Write to feature store
features.write.mode("overwrite").parquet("s3://ml-features/user_features/")
''',

    # ---------------------------------------------------------------------
    # Job 5: Churn prediction model scoring
    # ---------------------------------------------------------------------
    "jobs/churn_scoring.py": '''"""Score users with churn prediction model."""
from pyspark.sql import SparkSession
from pyspark.ml import PipelineModel

spark = SparkSession.builder.appName("ChurnScoring").getOrCreate()

# Read features
features = spark.read.parquet("s3://ml-features/user_features/")

# Read user dimensions for context
dim_users = spark.read.table("warehouse.dim_users")

# Load model and score
model = PipelineModel.load("s3://ml-models/churn_model/")
predictions = model.transform(features)

# Write predictions
predictions.write.mode("overwrite").saveAsTable("ml.churn_predictions")
''',

    # ---------------------------------------------------------------------
    # Streamlit Dashboard
    # ---------------------------------------------------------------------
    "dashboards/executive_dashboard.py": '''"""Executive metrics dashboard."""
import streamlit as st
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("Dashboard").getOrCreate()

# Load reporting data
daily_summary = spark.read.table("reporting.daily_summary")
churn_predictions = spark.read.table("ml.churn_predictions")

st.title("Executive Dashboard")
st.dataframe(daily_summary.toPandas())
st.dataframe(churn_predictions.toPandas())
''',
}


# =============================================================================
# Inline LineageGraph (standalone - no dependencies)
# =============================================================================

class LineageGraph:
    """Lightweight lineage graph for demo."""
    
    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._outgoing: Dict[str, Set[str]] = defaultdict(set)
        self._incoming: Dict[str, Set[str]] = defaultdict(set)
        self._edge_types: Dict[Tuple[str, str], str] = {}
    
    def add_node(self, node_id: str, **attrs) -> None:
        self._nodes[node_id] = attrs
    
    def add_edge(self, source: str, target: str, edge_type: str = "unknown") -> None:
        self._outgoing[source].add(target)
        self._incoming[target].add(source)
        self._edge_types[(source, target)] = edge_type
    
    def get_node(self, node_id: str) -> Dict:
        return self._nodes.get(node_id, {})
    
    def downstream(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """Find all affected nodes downstream."""
        visited = set()
        to_visit = [(node_id, 0)]
        
        while to_visit:
            current, depth = to_visit.pop(0)
            if current in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue
            visited.add(current)
            
            # Things that read from us
            for source in self._incoming.get(current, set()):
                et = self._edge_types.get((source, current), "").lower()
                if et == "reads":
                    to_visit.append((source, depth + 1))
            
            # Things we write to
            for target in self._outgoing.get(current, set()):
                et = self._edge_types.get((current, target), "").lower()
                if et in ("writes", "depends_on"):
                    to_visit.append((target, depth + 1))
        
        visited.discard(node_id)
        return visited
    
    def upstream(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """Find all source nodes upstream."""
        visited = set()
        to_visit = [(node_id, 0)]
        
        while to_visit:
            current, depth = to_visit.pop(0)
            if current in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue
            visited.add(current)
            
            # Things we read from
            for target in self._outgoing.get(current, set()):
                et = self._edge_types.get((current, target), "").lower()
                if et == "reads":
                    to_visit.append((target, depth + 1))
            
            # Things that write to us
            for source in self._incoming.get(current, set()):
                et = self._edge_types.get((source, current), "").lower()
                if et == "writes":
                    to_visit.append((source, depth + 1))
        
        visited.discard(node_id)
        return visited
    
    def trace(self, source: str, target: str) -> List[List[str]]:
        """Find paths between two nodes."""
        if source not in self._nodes or target not in self._nodes:
            return []
        
        paths = []
        queue = [(source, [source])]
        
        while queue:
            current, path = queue.pop(0)
            if current == target:
                paths.append(path)
                continue
            if len(path) > 15:
                continue
            
            for neighbor in self._outgoing.get(current, set()) | self._incoming.get(current, set()):
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))
        
        return paths
    
    def find_orphans(self) -> List[str]:
        """Find nodes with no connections."""
        return [n for n in self._nodes 
                if not self._outgoing.get(n) and not self._incoming.get(n)]
    
    def stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        by_type = defaultdict(int)
        for nid in self._nodes:
            if nid.startswith("data:"):
                by_type["data"] += 1
            elif nid.startswith(("file:", "job:")):
                by_type["code"] += 1
            else:
                by_type["other"] += 1
        
        edge_types = defaultdict(int)
        for (_, _), et in self._edge_types.items():
            edge_types[et] += 1
        
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edge_types),
            "nodes_by_type": dict(by_type),
            "edges_by_type": dict(edge_types),
        }
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [{"id": k, **v} for k, v in self._nodes.items()],
            "edges": [{"source": s, "target": t, "type": et} 
                     for (s, t), et in self._edge_types.items()],
            "stats": self.stats(),
        }


# =============================================================================
# Simple PySpark Parser (regex-based for demo)
# =============================================================================

import re

def parse_pyspark(content: str, file_path: str) -> Tuple[List[Dict], List[Dict]]:
    """Extract tables read/written from PySpark code."""
    nodes = []
    edges = []
    
    # Normalize backslash continuations
    text = content.replace('\\\n', ' ')
    
    file_id = f"file:{file_path}"
    file_name = Path(file_path).stem
    nodes.append({"id": file_id, "name": file_name, "type": "code_file"})
    
    # Patterns for reading tables
    read_patterns = [
        r'spark\.read\.table\(["\']([^"\']+)["\']\)',
        r'spark\.table\(["\']([^"\']+)["\']\)',
        r'\.load\(["\']([^"\']+)["\']\)',
        r'\.parquet\(["\']([^"\']+)["\']\)',
    ]
    
    # Patterns for writing tables
    write_patterns = [
        r'\.saveAsTable\(["\']([^"\']+)["\']\)',
        r'\.insertInto\(["\']([^"\']+)["\']\)',
        r'\.save\(["\']([^"\']+)["\']\)',
        r'\.parquet\(["\']([^"\']+)["\']\)',  # Context determines read vs write
    ]
    
    # Find reads
    for pattern in read_patterns:
        for match in re.finditer(pattern, text):
            table = match.group(1)
            table_id = f"data:{table.replace('://', ':')}"
            nodes.append({"id": table_id, "name": table, "type": "data_asset"})
            edges.append({"source": file_id, "target": table_id, "type": "reads"})
    
    # Find writes (look for .write before .save/.saveAsTable)
    write_block_pattern = r'\.write\s*(?:\.[a-zA-Z_]+\s*\([^)]*\)\s*)*\.(saveAsTable|save|parquet)\(["\']([^"\']+)["\']\)'
    for match in re.finditer(write_block_pattern, text):
        table = match.group(2)
        table_id = f"data:{table.replace('://', ':')}"
        nodes.append({"id": table_id, "name": table, "type": "data_asset"})
        edges.append({"source": file_id, "target": table_id, "type": "writes"})
    
    return nodes, edges


# =============================================================================
# HTML Visualization Generator
# =============================================================================

def generate_html(graph: LineageGraph) -> str:
    """Generate interactive HTML visualization."""
    data = graph.to_dict()
    
    # Prepare vis.js data
    vis_nodes = []
    vis_edges = []
    
    colors = {
        "data": "#4CAF50",    # Green
        "code": "#2196F3",    # Blue  
        "config": "#FF9800",  # Orange
        "infra": "#9C27B0",   # Purple
    }
    
    for node in data["nodes"]:
        node_id = node.get("id", "")
        name = node.get("name", node_id)
        
        # Determine category
        if node_id.startswith("data:"):
            category = "data"
        elif node_id.startswith(("file:", "job:")):
            category = "code"
        elif node_id.startswith("env:"):
            category = "config"
        else:
            category = "code"
        
        # Short label
        if "." in name:
            label = name.split(".")[-1]
        elif "/" in name:
            label = name.split("/")[-1]
        else:
            label = name
        
        vis_nodes.append({
            "id": node_id,
            "label": label,
            "title": node_id,
            "color": colors.get(category, "#757575"),
            "group": category,
        })
    
    for edge in data["edges"]:
        vis_edges.append({
            "from": edge["source"],
            "to": edge["target"],
            "arrows": "to",
            "dashes": edge["type"] == "reads",
            "title": edge["type"],
        })
    
    return f'''<!DOCTYPE html>
<html>
<head>
    <title>jnkn Lineage Graph</title>
    <meta charset="utf-8">
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        * {{ box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            margin: 0;
            background: #1a1a2e;
            color: #eee;
        }}
        #header {{
            padding: 15px 20px;
            background: #16213e;
            border-bottom: 1px solid #0f3460;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        #header h1 {{
            margin: 0;
            font-size: 1.4em;
            color: #e94560;
        }}
        .stat {{
            background: #0f3460;
            padding: 8px 15px;
            border-radius: 5px;
            margin-left: 10px;
        }}
        .stat-value {{ font-weight: bold; color: #e94560; }}
        #container {{ display: flex; height: calc(100vh - 70px); }}
        #graph {{ flex: 1; }}
        #sidebar {{
            width: 320px;
            background: #16213e;
            border-left: 1px solid #0f3460;
            padding: 15px;
            overflow-y: auto;
        }}
        #search {{
            width: 100%;
            padding: 12px;
            border: 1px solid #0f3460;
            border-radius: 5px;
            background: #1a1a2e;
            color: #eee;
            font-size: 14px;
        }}
        #search:focus {{ outline: none; border-color: #e94560; }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin: 15px 0;
            padding: 10px;
            background: #0f3460;
            border-radius: 5px;
        }}
        .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 0.85em; }}
        .legend-color {{ width: 14px; height: 14px; border-radius: 3px; }}
        #node-info {{ display: none; margin-top: 20px; }}
        #node-info.active {{ display: block; }}
        #node-info h2 {{
            margin: 0 0 15px 0;
            font-size: 1.1em;
            color: #e94560;
            border-bottom: 1px solid #0f3460;
            padding-bottom: 10px;
        }}
        .info-row {{ margin: 12px 0; }}
        .info-label {{ color: #888; font-size: 0.75em; text-transform: uppercase; }}
        .info-value {{ color: #eee; word-break: break-all; margin-top: 3px; font-family: monospace; }}
        .impact-section {{ margin: 15px 0; }}
        .impact-section h3 {{ font-size: 0.9em; color: #e94560; margin: 0 0 8px 0; }}
        .impact-list {{
            list-style: none;
            padding: 0;
            margin: 0;
            font-size: 0.8em;
            max-height: 180px;
            overflow-y: auto;
            background: #0f3460;
            border-radius: 5px;
            padding: 8px;
        }}
        .impact-list li {{
            padding: 5px 0;
            color: #ccc;
            border-bottom: 1px solid #16213e;
            font-family: monospace;
        }}
        .impact-list li:last-child {{ border-bottom: none; }}
        .help-text {{
            font-size: 0.8em;
            color: #666;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #0f3460;
        }}
        .highlight {{ color: #e94560; font-weight: bold; }}
    </style>
</head>
<body>
    <div id="header">
        <h1>🔗 jnkn Lineage Graph</h1>
        <div style="display:flex">
            <div class="stat">Nodes: <span class="stat-value">{len(vis_nodes)}</span></div>
            <div class="stat">Edges: <span class="stat-value">{len(vis_edges)}</span></div>
        </div>
    </div>
    <div id="container">
        <div id="graph"></div>
        <div id="sidebar">
            <input type="text" id="search" placeholder="🔍 Search nodes (e.g. 'dim_users')...">
            
            <div class="legend">
                <div class="legend-item"><div class="legend-color" style="background:#4CAF50"></div> Data</div>
                <div class="legend-item"><div class="legend-color" style="background:#2196F3"></div> Code</div>
                <div class="legend-item"><div class="legend-color" style="background:#FF9800"></div> Config</div>
                <div class="legend-item"><div class="legend-color" style="background:#9C27B0"></div> Infra</div>
            </div>
            
            <div id="node-info">
                <h2>📍 Node Details</h2>
                <div class="info-row">
                    <div class="info-label">ID</div>
                    <div class="info-value" id="info-id"></div>
                </div>
                <div class="info-row">
                    <div class="info-label">Label</div>
                    <div class="info-value" id="info-name"></div>
                </div>
                <div class="impact-section">
                    <h3>⬆️ Upstream <span id="upstream-count"></span></h3>
                    <ul class="impact-list" id="upstream-list"></ul>
                </div>
                <div class="impact-section">
                    <h3>⬇️ Downstream <span id="downstream-count"></span></h3>
                    <ul class="impact-list" id="downstream-list"></ul>
                </div>
            </div>
            
            <div class="help-text">
                <strong>How to use:</strong><br>
                • Click a node to see its dependencies<br>
                • Search to find specific tables/jobs<br>
                • Dashed lines = reads, solid = writes<br>
                • Scroll to zoom, drag to pan
            </div>
        </div>
    </div>
    
    <script>
        const nodesData = {json.dumps(vis_nodes)};
        const edgesData = {json.dumps(vis_edges)};
        
        const nodes = new vis.DataSet(nodesData);
        const edges = new vis.DataSet(edgesData);
        
        const options = {{
            nodes: {{
                shape: 'box',
                font: {{ color: '#fff', size: 13 }},
                borderWidth: 0,
                shadow: {{ enabled: true, size: 5 }},
                margin: 10,
            }},
            edges: {{
                color: {{ color: '#555', highlight: '#e94560' }},
                smooth: {{ type: 'cubicBezier', roundness: 0.5 }},
                width: 2,
            }},
            physics: {{
                stabilization: {{ iterations: 150 }},
                barnesHut: {{
                    gravitationalConstant: -3000,
                    springLength: 200,
                    springConstant: 0.04,
                }},
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
                zoomView: true,
            }},
        }};
        
        const network = new vis.Network(document.getElementById('graph'), {{ nodes, edges }}, options);
        
        // Build adjacency lists
        const outgoing = {{}};
        const incoming = {{}};
        const edgeTypes = {{}};
        
        edgesData.forEach(e => {{
            if (!outgoing[e.from]) outgoing[e.from] = [];
            if (!incoming[e.to]) incoming[e.to] = [];
            outgoing[e.from].push(e.to);
            incoming[e.to].push(e.from);
            edgeTypes[e.from + '|' + e.to] = e.title;
        }});
        
        function getUpstream(id, visited = new Set()) {{
            if (visited.has(id)) return [];
            visited.add(id);
            let results = [];
            
            (outgoing[id] || []).forEach(target => {{
                const et = (edgeTypes[id + '|' + target] || '').toLowerCase();
                if (et === 'reads') {{
                    results.push(target);
                    results = results.concat(getUpstream(target, visited));
                }}
            }});
            
            (incoming[id] || []).forEach(source => {{
                const et = (edgeTypes[source + '|' + id] || '').toLowerCase();
                if (et === 'writes') {{
                    results.push(source);
                    results = results.concat(getUpstream(source, visited));
                }}
            }});
            
            return [...new Set(results)];
        }}
        
        function getDownstream(id, visited = new Set()) {{
            if (visited.has(id)) return [];
            visited.add(id);
            let results = [];
            
            (incoming[id] || []).forEach(source => {{
                const et = (edgeTypes[source + '|' + id] || '').toLowerCase();
                if (et === 'reads') {{
                    results.push(source);
                    results = results.concat(getDownstream(source, visited));
                }}
            }});
            
            (outgoing[id] || []).forEach(target => {{
                const et = (edgeTypes[id + '|' + target] || '').toLowerCase();
                if (et === 'writes' || et === 'depends_on') {{
                    results.push(target);
                    results = results.concat(getDownstream(target, visited));
                }}
            }});
            
            return [...new Set(results)];
        }}
        
        network.on('click', function(params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const node = nodesData.find(n => n.id === nodeId);
                
                if (node) {{
                    document.getElementById('node-info').classList.add('active');
                    document.getElementById('info-id').textContent = node.id;
                    document.getElementById('info-name').textContent = node.label;
                    
                    const upstream = getUpstream(nodeId);
                    const downstream = getDownstream(nodeId);
                    
                    document.getElementById('upstream-count').textContent = '(' + upstream.length + ')';
                    document.getElementById('downstream-count').textContent = '(' + downstream.length + ')';
                    
                    document.getElementById('upstream-list').innerHTML = 
                        upstream.length 
                            ? upstream.map(id => '<li>' + id.replace('data:', '').replace('file:', '') + '</li>').join('') 
                            : '<li style="color:#666">None (this is a source)</li>';
                    document.getElementById('downstream-list').innerHTML = 
                        downstream.length 
                            ? downstream.map(id => '<li>' + id.replace('data:', '').replace('file:', '') + '</li>').join('') 
                            : '<li style="color:#666">None (this is a leaf)</li>';
                    
                    const connected = new Set([nodeId, ...upstream, ...downstream]);
                    nodes.update(nodesData.map(n => ({{
                        id: n.id,
                        opacity: connected.has(n.id) ? 1 : 0.15
                    }})));
                }}
            }} else {{
                nodes.update(nodesData.map(n => ({{ id: n.id, opacity: 1 }})));
            }}
        }});
        
        document.getElementById('search').addEventListener('input', function(e) {{
            const query = e.target.value.toLowerCase();
            
            if (query) {{
                const matching = nodesData.filter(n => 
                    n.id.toLowerCase().includes(query) || 
                    n.label.toLowerCase().includes(query)
                );
                
                if (matching.length > 0) {{
                    network.selectNodes(matching.map(n => n.id));
                    network.fit({{ nodes: matching.map(n => n.id), animation: true }});
                }}
            }} else {{
                network.unselectAll();
                network.fit({{ animation: true }});
            }}
        }});
        
        // Fit to view after stabilization
        network.once('stabilizationIterationsDone', function() {{
            network.fit({{ animation: true }});
        }});
    </script>
</body>
</html>'''


# =============================================================================
# Demo Runner
# =============================================================================

def main():
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║   🔗 jnkn CLI DEMO - Data Lineage Visualization         ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Create temp directory with sample files
    tmp_dir = Path(tempfile.mkdtemp(prefix="jnkn_demo_"))
    print(f"📁 Creating sample pipeline in: {tmp_dir}\n")
    
    for rel_path, content in SAMPLE_FILES.items():
        file_path = tmp_dir / rel_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content)
        print(f"   ✓ {rel_path}")
    
    # Parse files and build graph
    print(f"\n🔍 Scanning files...\n")
    
    graph = LineageGraph()
    
    for rel_path in SAMPLE_FILES.keys():
        file_path = tmp_dir / rel_path
        content = file_path.read_text()
        
        nodes, edges = parse_pyspark(content, rel_path)
        
        for node in nodes:
            graph.add_node(node["id"], **node)
        for edge in edges:
            graph.add_edge(edge["source"], edge["target"], edge["type"])
        
        print(f"   → {rel_path}: {len(nodes)} nodes, {len(edges)} edges")
    
    # Show stats
    stats = graph.stats()
    print(f"""
📊 Graph Statistics
═══════════════════════════════════════
   Total nodes: {stats['total_nodes']}
   Total edges: {stats['total_edges']}
   
   Nodes by type:
      Data:  {stats['nodes_by_type'].get('data', 0)}
      Code:  {stats['nodes_by_type'].get('code', 0)}
   
   Edges by type:
      Reads:  {stats['edges_by_type'].get('reads', 0)}
      Writes: {stats['edges_by_type'].get('writes', 0)}
""")
    
    # Demo: Impact Analysis
    print("💥 Impact Analysis Demo")
    print("═" * 55)
    
    target = "data:warehouse.dim_users"
    print(f"\n   Question: What breaks if we change 'warehouse.dim_users'?\n")
    
    downstream = graph.downstream(target)
    upstream = graph.upstream(target)
    
    print(f"   ⬆️  Upstream (sources): {len(upstream)}")
    if upstream:
        for node_id in sorted(upstream)[:5]:
            name = node_id.replace("data:", "").replace("file:", "")
            print(f"      • {name}")
    else:
        print("      (none - this is a source table)")
    
    print(f"\n   ⬇️  Downstream (affected): {len(downstream)}")
    for node_id in sorted(downstream)[:10]:
        name = node_id.replace("data:", "").replace("file:", "")
        print(f"      • {name}")
    
    print(f"\n   Total affected: {len(upstream) + len(downstream)} nodes")
    
    # Generate HTML
    output_path = Path("lineage.html")
    html = generate_html(graph)
    output_path.write_text(html)
    
    # Also save JSON
    json_path = Path("lineage.json")
    json_path.write_text(json.dumps(graph.to_dict(), indent=2))
    
    print(f"""
🎨 Generated Visualization
═══════════════════════════════════════
   
   ✓ {output_path.absolute()}
   ✓ {json_path.absolute()}

📖 How to Use the Graph:

   1. Open lineage.html in your browser
   
   2. Click on any node to see:
      • Its upstream dependencies (what feeds it)
      • Its downstream impact (what it affects)
      • Unrelated nodes fade out
   
   3. Try clicking on:
      • 'dim_users' - see how it affects the whole pipeline
      • 'daily_summary' - see what feeds into reporting
      • 'churn_predictions' - see the ML pipeline lineage
   
   4. Use the search box to find specific tables
   
   5. Zoom with scroll, pan by dragging

🚀 This is what 'jnkn scan' + 'jnkn graph' does!

""")
    
    # Cleanup
    # shutil.rmtree(tmp_dir)  # Uncomment to cleanup temp files


if __name__ == "__main__":
    main()