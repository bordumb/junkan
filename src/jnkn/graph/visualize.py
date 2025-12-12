"""
Visualization Engine.

Generates interactive HTML graphs using vis.js.
Embeds the graph data and semantic traversal logic directly into the HTML
so it can be viewed offline without a backend server.
"""

import json
import webbrowser
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..core.interfaces import IGraph

# Minimal template with embedded logic
HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <title>Jnkn Graph Visualization</title>
  <script type="text/javascript" src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style type="text/css">
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; margin: 0; padding: 0; overflow: hidden; }
    #mynetwork { width: 100vw; height: 100vh; border: none; background-color: #f5f5f5; }
    #controls { position: absolute; top: 10px; left: 10px; z-index: 100; background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); width: 300px; }
    h2 { margin-top: 0; font-size: 18px; color: #333; }
    .legend-item { display: flex; align-items: center; margin-bottom: 5px; font-size: 12px; }
    .dot { width: 10px; height: 10px; border-radius: 50%; margin-right: 8px; }
    .btn { display: block; width: 100%; padding: 8px; margin-top: 10px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; text-align: center; }
    .btn:hover { background: #0056b3; }
    #status { margin-top: 10px; font-size: 12px; color: #666; font-style: italic; }
  </style>
</head>
<body>
<div id="controls">
  <h2>Dependency Graph</h2>
  <div id="legend">
    <div class="legend-item"><div class="dot" style="background:#FF9800"></div>Config / Env Var</div>
    <div class="legend-item"><div class="dot" style="background:#E91E63"></div>Infrastructure</div>
    <div class="legend-item"><div class="dot" style="background:#4CAF50"></div>Code</div>
    <div class="legend-item"><div class="dot" style="background:#2196F3"></div>Data Asset</div>
  </div>
  <hr style="border:0; border-top:1px solid #eee; margin:10px 0;">
  <div>
    <label style="font-size:12px; font-weight:bold;">Impact Analysis</label>
    <p style="font-size:11px; color:#666; margin: 5px 0;">Click a node to highlight its blast radius.</p>
  </div>
  <div id="status">Ready</div>
</div>

<div id="mynetwork"></div>

<script type="text/javascript">
  // 1. Data Injection
  const graphData = __GRAPH_DATA__;

  // 2. Semantic Logic (Mirrors Python IGraph logic)
  const FORWARD_IMPACT_TYPES = new Set(['provides', 'writes', 'flows_to', 'provisions', 'outputs']);
  const REVERSE_IMPACT_TYPES = new Set(['reads', 'depends_on', 'calls']);

  // 3. Process Data for Vis.js
  const nodes = new vis.DataSet(graphData.nodes.map(n => ({
    id: n.id,
    label: n.name || n.id,
    group: inferGroup(n.type, n.id),
    title: `ID: ${n.id}<br>Type: ${n.type}`
  })));

  const edges = new vis.DataSet(graphData.edges.map(e => ({
    from: e.source_id,
    to: e.target_id,
    arrows: 'to',
    title: e.type,
    color: { color: '#ccc' },
    dashes: REVERSE_IMPACT_TYPES.has((e.type || '').toLowerCase()) 
  })));

  function inferGroup(type, id) {
    const t = (type || "").toLowerCase();
    const i = (id || "").toLowerCase();
    if (t.includes('env') || t.includes('config') || i.startsWith('env:')) return 'config';
    if (t.includes('infra') || i.startsWith('infra:')) return 'infra';
    if (t.includes('file') || t.includes('code') || i.startsWith('file:')) return 'code';
    if (t.includes('data') || i.startsWith('data:')) return 'data';
    return 'other';
  }

  // 4. Initialize Network
  const container = document.getElementById('mynetwork');
  const data = { nodes: nodes, edges: edges };
  const options = {
    nodes: { shape: 'dot', size: 16, font: { size: 14 } },
    groups: {
      config: { color: { background: '#FF9800', border: '#F57C00' } },
      infra:  { color: { background: '#E91E63', border: '#C2185B' } },
      code:   { color: { background: '#4CAF50', border: '#388E3C' } },
      data:   { color: { background: '#2196F3', border: '#1976D2' } },
      other:  { color: { background: '#9E9E9E', border: '#757575' } }
    },
    physics: {
      stabilization: false,
      barnesHut: { gravitationalConstant: -2000, springConstant: 0.04 }
    }
  };
  const network = new vis.Network(container, data, options);

  // 5. Interactive Blast Radius Logic
  network.on("click", function (params) {
    if (params.nodes.length === 0) {
      resetHighlight();
      return;
    }
    const selectedId = params.nodes[0];
    highlightBlastRadius(selectedId);
  });

  function resetHighlight() {
    nodes.forEach(n => {
      nodes.update({ id: n.id, color: null, opacity: 1 });
    });
    edges.forEach(e => {
      edges.update({ id: e.id, color: { color: '#ccc' }, opacity: 1 });
    });
    document.getElementById('status').innerText = "Ready";
  }

  function highlightBlastRadius(sourceId) {
    // Perform semantic BFS (Client-side)
    const impacted = new Set([sourceId]);
    const queue = [sourceId];
    const visitedEdgeIds = new Set();

    while (queue.length > 0) {
      const current = queue.shift();
      
      // Find connected edges
      const connectedEdges = edges.get({
        filter: function (item) {
          return item.from === current || item.to === current;
        }
      });

      connectedEdges.forEach(edge => {
        const type = (edge.title || "").toLowerCase();
        let neighbor = null;

        // Forward Impact (Downstream)
        if (edge.from === current && FORWARD_IMPACT_TYPES.has(type)) {
          neighbor = edge.to;
        }
        // Reverse Impact (Upstream Consumer)
        else if (edge.to === current && REVERSE_IMPACT_TYPES.has(type)) {
          neighbor = edge.from;
        }

        if (neighbor && !impacted.has(neighbor)) {
          impacted.add(neighbor);
          queue.push(neighbor);
          visitedEdgeIds.add(edge.id);
        } else if (neighbor && impacted.has(neighbor)) {
           // Edge between already impacted nodes is part of the blast radius visual
           visitedEdgeIds.add(edge.id);
        }
      });
    }

    // Apply Styles
    nodes.forEach(n => {
      if (impacted.has(n.id)) {
        nodes.update({ id: n.id, opacity: 1 });
      } else {
        nodes.update({ id: n.id, color: { background: '#eee', border: '#ddd' }, opacity: 0.3 });
      }
    });

    edges.forEach(e => {
      if (visitedEdgeIds.has(e.id)) {
        edges.update({ id: e.id, color: { color: '#ff0000' }, width: 2 });
      } else {
        edges.update({ id: e.id, color: { color: '#eee' }, opacity: 0.1 });
      }
    });

    document.getElementById('status').innerText = `Blast Radius: ${impacted.size} nodes impacted`;
  }
</script>
</body>
</html>
"""


def _json_default(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def generate_html(graph: IGraph) -> str:
    """
    Generate the HTML content for the graph visualization.
    """
    # Serialize graph to dict using the new helper
    # We use the to_dict method on DependencyGraph if available, or build it manually
    if hasattr(graph, "to_dict"):
        graph_data = graph.to_dict()
    else:
        # Fallback for generic IGraph
        graph_data = {
            "nodes": [n.model_dump() for n in graph.iter_nodes()],
            "edges": [e.model_dump() for e in graph.iter_edges()],
        }

    # Dump to JSON string for JS injection, handling datetime objects
    json_data = json.dumps(graph_data, default=_json_default)

    # Inject into template
    return HTML_TEMPLATE.replace("__GRAPH_DATA__", json_data)


def open_visualization(graph: IGraph, output_path: str = "graph.html") -> str:
    """
    Generate and open the visualization in the browser.
    """
    html_content = generate_html(graph)

    # Save to file
    out_file = Path(output_path)
    out_file.write_text(html_content, encoding="utf-8")

    # Open in browser
    abs_path = out_file.resolve().as_uri()
    webbrowser.open(abs_path)

    return str(out_file)
