"""
Visualization Module - HTML and DOT export for lineage graphs.

Generates interactive HTML visualizations using vis.js.
"""

import json
from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from .lineage import LineageGraph


def generate_html(graph: "LineageGraph") -> str:
    """
    Generate interactive HTML visualization.
    
    Uses vis.js for graph rendering with:
    - Color-coded nodes by type
    - Click to see upstream/downstream
    - Search functionality
    - Zoom and pan
    """
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
        
        # Determine category from ID prefix
        if node_id.startswith("data:"):
            category = "data"
        elif node_id.startswith(("file:", "job:")):
            category = "code"
        elif node_id.startswith("env:"):
            category = "config"
        elif node_id.startswith("infra:"):
            category = "infra"
        else:
            category = "code"
        
        # Short label for display
        if "." in name:
            label = name.split(".")[-1]
        elif "/" in name:
            label = name.split("/")[-1]
        else:
            label = name
        
        vis_nodes.append({
            "id": node_id,
            "label": label,
            "title": f"{node_id}",
            "color": colors.get(category, "#757575"),
            "group": category,
        })
    
    for edge in data["edges"]:
        vis_edges.append({
            "from": edge["source"],
            "to": edge["target"],
            "arrows": "to",
            "dashes": edge["type"] in ("reads", "READS"),
            "title": edge["type"],
        })
    
    return _html_template(vis_nodes, vis_edges, data.get("stats", {}))


def _html_template(nodes: List[Dict], edges: List[Dict], 
                   stats: Dict[str, Any]) -> str:
    """Generate the HTML template."""
    node_count = len(nodes)
    edge_count = len(edges)
    
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
            padding: 0;
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
        #stats {{
            display: flex;
            gap: 15px;
        }}
        .stat {{
            background: #0f3460;
            padding: 8px 15px;
            border-radius: 5px;
            font-size: 0.9em;
        }}
        .stat-value {{
            font-weight: bold;
            color: #e94560;
        }}
        #container {{
            display: flex;
            height: calc(100vh - 70px);
        }}
        #graph {{
            flex: 1;
            background: #1a1a2e;
        }}
        #sidebar {{
            width: 300px;
            background: #16213e;
            border-left: 1px solid #0f3460;
            padding: 15px;
            overflow-y: auto;
        }}
        #search {{
            width: 100%;
            padding: 10px;
            border: 1px solid #0f3460;
            border-radius: 5px;
            background: #1a1a2e;
            color: #eee;
            font-size: 14px;
        }}
        #search:focus {{
            outline: none;
            border-color: #e94560;
        }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 12px;
            margin: 15px 0;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 6px;
            font-size: 0.85em;
        }}
        .legend-color {{
            width: 14px;
            height: 14px;
            border-radius: 3px;
        }}
        #node-info {{
            display: none;
            margin-top: 20px;
        }}
        #node-info.active {{
            display: block;
        }}
        #node-info h2 {{
            margin: 0 0 15px 0;
            font-size: 1.1em;
            color: #e94560;
            border-bottom: 1px solid #0f3460;
            padding-bottom: 10px;
        }}
        .info-row {{
            margin: 12px 0;
        }}
        .info-label {{
            color: #888;
            font-size: 0.75em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .info-value {{
            color: #eee;
            word-break: break-all;
            margin-top: 3px;
        }}
        .impact-section {{
            margin: 15px 0;
        }}
        .impact-section h3 {{
            font-size: 0.9em;
            color: #e94560;
            margin: 0 0 8px 0;
        }}
        .impact-list {{
            list-style: none;
            padding: 0;
            margin: 0;
            font-size: 0.85em;
            max-height: 200px;
            overflow-y: auto;
        }}
        .impact-list li {{
            padding: 4px 0;
            color: #ccc;
            border-bottom: 1px solid #0f3460;
        }}
        .impact-list li:last-child {{
            border-bottom: none;
        }}
        .help-text {{
            font-size: 0.8em;
            color: #666;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #0f3460;
        }}
    </style>
</head>
<body>
    <div id="header">
        <h1>🔗 jnkn Lineage Graph</h1>
        <div id="stats">
            <div class="stat">Nodes: <span class="stat-value">{node_count}</span></div>
            <div class="stat">Edges: <span class="stat-value">{edge_count}</span></div>
        </div>
    </div>
    <div id="container">
        <div id="graph"></div>
        <div id="sidebar">
            <input type="text" id="search" placeholder="Search nodes...">
            
            <div class="legend">
                <div class="legend-item">
                    <div class="legend-color" style="background:#4CAF50"></div> Data
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background:#2196F3"></div> Code
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background:#FF9800"></div> Config
                </div>
                <div class="legend-item">
                    <div class="legend-color" style="background:#9C27B0"></div> Infra
                </div>
            </div>
            
            <div id="node-info">
                <h2>Node Details</h2>
                <div class="info-row">
                    <div class="info-label">ID</div>
                    <div class="info-value" id="info-id"></div>
                </div>
                <div class="info-row">
                    <div class="info-label">Name</div>
                    <div class="info-value" id="info-name"></div>
                </div>
                <div class="impact-section">
                    <h3>⬆️ Upstream</h3>
                    <ul class="impact-list" id="upstream-list"></ul>
                </div>
                <div class="impact-section">
                    <h3>⬇️ Downstream</h3>
                    <ul class="impact-list" id="downstream-list"></ul>
                </div>
            </div>
            
            <div class="help-text">
                Click a node to see details.<br>
                Use search to find specific nodes.
            </div>
        </div>
    </div>
    
    <script>
        // Graph data
        const nodesData = {json.dumps(nodes)};
        const edgesData = {json.dumps(edges)};
        
        // Create vis.js datasets
        const nodes = new vis.DataSet(nodesData);
        const edges = new vis.DataSet(edgesData);
        
        // Network options
        const options = {{
            nodes: {{
                shape: 'box',
                font: {{ color: '#fff', size: 12 }},
                borderWidth: 0,
                shadow: true,
            }},
            edges: {{
                color: {{ color: '#555', highlight: '#e94560' }},
                smooth: {{ type: 'cubicBezier' }},
            }},
            physics: {{
                stabilization: {{ iterations: 100 }},
                barnesHut: {{
                    gravitationalConstant: -2000,
                    springLength: 150,
                }},
            }},
            interaction: {{
                hover: true,
                tooltipDelay: 100,
            }},
        }};
        
        // Create network
        const container = document.getElementById('graph');
        const network = new vis.Network(container, {{ nodes, edges }}, options);
        
        // Build adjacency lists for impact analysis
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
        
        // Upstream traversal
        function getUpstream(id, visited = new Set()) {{
            if (visited.has(id)) return [];
            visited.add(id);
            let results = [];
            
            // Things we read from
            (outgoing[id] || []).forEach(target => {{
                const et = (edgeTypes[id + '|' + target] || '').toLowerCase();
                if (et === 'reads') {{
                    results.push(target);
                    results = results.concat(getUpstream(target, visited));
                }}
            }});
            
            // Things that write to us
            (incoming[id] || []).forEach(source => {{
                const et = (edgeTypes[source + '|' + id] || '').toLowerCase();
                if (et === 'writes') {{
                    results.push(source);
                    results = results.concat(getUpstream(source, visited));
                }}
            }});
            
            return [...new Set(results)];
        }}
        
        // Downstream traversal
        function getDownstream(id, visited = new Set()) {{
            if (visited.has(id)) return [];
            visited.add(id);
            let results = [];
            
            // Things that read from us
            (incoming[id] || []).forEach(source => {{
                const et = (edgeTypes[source + '|' + id] || '').toLowerCase();
                if (et === 'reads') {{
                    results.push(source);
                    results = results.concat(getDownstream(source, visited));
                }}
            }});
            
            // Things we write to or depend on
            (outgoing[id] || []).forEach(target => {{
                const et = (edgeTypes[id + '|' + target] || '').toLowerCase();
                if (et === 'writes' || et === 'depends_on') {{
                    results.push(target);
                    results = results.concat(getDownstream(target, visited));
                }}
            }});
            
            return [...new Set(results)];
        }}
        
        // Click handler
        network.on('click', function(params) {{
            if (params.nodes.length > 0) {{
                const nodeId = params.nodes[0];
                const node = nodesData.find(n => n.id === nodeId);
                
                if (node) {{
                    // Show info panel
                    document.getElementById('node-info').classList.add('active');
                    document.getElementById('info-id').textContent = node.id;
                    document.getElementById('info-name').textContent = node.label;
                    
                    // Calculate impact
                    const upstream = getUpstream(nodeId);
                    const downstream = getDownstream(nodeId);
                    
                    // Update lists
                    document.getElementById('upstream-list').innerHTML = 
                        upstream.length 
                            ? upstream.map(id => '<li>' + id + '</li>').join('') 
                            : '<li style="color:#666">None</li>';
                    document.getElementById('downstream-list').innerHTML = 
                        downstream.length 
                            ? downstream.map(id => '<li>' + id + '</li>').join('') 
                            : '<li style="color:#666">None</li>';
                    
                    // Highlight connected nodes
                    const connected = new Set([nodeId, ...upstream, ...downstream]);
                    nodes.update(nodesData.map(n => ({{
                        id: n.id,
                        opacity: connected.has(n.id) ? 1 : 0.2
                    }})));
                }}
            }} else {{
                // Reset highlighting
                nodes.update(nodesData.map(n => ({{ id: n.id, opacity: 1 }})));
            }}
        }});
        
        // Search handler
        document.getElementById('search').addEventListener('input', function(e) {{
            const query = e.target.value.toLowerCase();
            
            if (query) {{
                const matching = nodesData.filter(n => 
                    n.id.toLowerCase().includes(query) || 
                    n.label.toLowerCase().includes(query)
                );
                
                if (matching.length > 0) {{
                    network.selectNodes(matching.map(n => n.id));
                    network.fit({{ 
                        nodes: matching.map(n => n.id), 
                        animation: true 
                    }});
                }}
            }} else {{
                network.unselectAll();
            }}
        }});
    </script>
</body>
</html>'''