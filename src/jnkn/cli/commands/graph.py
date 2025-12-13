"""
Graph Command - Generate interactive visualization.

Creates an HTML file with an interactive graph using vis.js,
or outputs raw JSON for IDE integrations.
"""

import json
import sys
from pathlib import Path

import click

# Adjust imports based on your actual project structure
from ..utils import echo_error, echo_info, echo_success, load_graph


@click.command()
@click.option("-i", "--input", "graph_file", default=".", help="Input graph JSON file or directory")
@click.option("-o", "--output", default="lineage.html", help="Output file (.html or .dot) for file export")
@click.option("--json", "json_mode", is_flag=True, help="Output graph data as JSON to stdout (for VS Code)")
def graph(graph_file: str, output: str, json_mode: bool):
    """
    Generate interactive visualization or raw data.
    """
    g_wrapper = load_graph(graph_file)
    
    if g_wrapper is None:
        if json_mode:
            click.echo(json.dumps({
                "meta": {"status": "error"},
                "error": {"message": "Graph not found. Run 'jnkn scan' first."}
            }))
        return

    # Unwrap the inner graph object 
    # The error showed 'DependencyGraph' has no 'nodes'. 
    # It likely wraps the real graph (rustworkx/networkx) in an attribute.
    if hasattr(g_wrapper, "graph"):
        g = g_wrapper.graph
    elif hasattr(g_wrapper, "_graph"):
        g = g_wrapper._graph
    else:
        # Fallback: assume the wrapper IS the graph (e.g. if it changed types)
        g = g_wrapper

    if json_mode:
        data = {
            "nodes": [],
            "edges": []
        }

        try:
            # STRATEGY 1: NetworkX Style (G.nodes(data=True))
            if hasattr(g, "nodes") and callable(g.nodes):
                # Check if it supports data=True (NetworkX) or just returns list (rustworkx)
                try:
                    # Try NetworkX iteration first
                    for n, d in g.nodes(data=True):
                        data["nodes"].append({
                            "id": n,
                            "name": d.get("name", n),
                            "type": d.get("type", "unknown")
                        })
                    for u, v, d in g.edges(data=True):
                        data["edges"].append({
                            "source_id": u,
                            "target_id": v,
                            "confidence": d.get("confidence", 1.0)
                        })
                except TypeError:
                     # Fallback for rustworkx (nodes() returns list of payloads)
                     # In rustworkx, nodes are often objects, and indices are integers
                     nodes = g.nodes()
                     # If nodes are objects with attributes:
                     for i, node_obj in enumerate(nodes):
                         # If node_obj is a dict or object
                         nid = getattr(node_obj, "id", str(i))
                         name = getattr(node_obj, "name", str(node_obj))
                         ntype = getattr(node_obj, "type", "unknown")
                         
                         data["nodes"].append({
                             "id": nid,
                             "name": name,
                             "type": ntype
                         })
                     
                     # Edges in rustworkx: g.edge_list() or g.edges()
                     # We need endpoints. g.edge_index_map() gives (src, target, data)
                     if hasattr(g, "edge_index_map"):
                         for _, (src_idx, tgt_idx, edge_data) in g.edge_index_map().items():
                             # We need to map indices back to node IDs
                             src_node = nodes[src_idx]
                             tgt_node = nodes[tgt_idx]
                             src_id = getattr(src_node, "id", str(src_idx))
                             tgt_id = getattr(tgt_node, "id", str(tgt_idx))
                             
                             conf = getattr(edge_data, "confidence", 1.0) if hasattr(edge_data, "confidence") else 1.0
                             
                             data["edges"].append({
                                 "source_id": src_id,
                                 "target_id": tgt_id,
                                 "confidence": conf
                             })

            # STRATEGY 2: Simple Iteration (for list-like objects)
            else:
                 # If it really doesn't have .nodes(), try iterating directly?
                 # This is unlikely for a graph object, but safe fallback.
                 pass

        except Exception as e:
            click.echo(json.dumps({
                "meta": {"status": "error"},
                "error": {"message": f"Failed to serialize graph: {str(e)}", "type": str(type(g))}
            }))
            return

        # Output strictly JSON to stdout
        click.echo(json.dumps({
            "meta": {"status": "success"},
            "data": data
        }))
        return

    # 3. Handle File Export (Original Logic)
    # Note: Use g_wrapper here as export_html likely belongs to the wrapper class
    output_path = Path(output)

    if output_path.suffix == ".html":
        # Check if wrapper has export, otherwise try to shim it
        if hasattr(g_wrapper, "export_html"):
            g_wrapper.export_html(output_path)
            echo_success(f"Generated: {output_path}")
            echo_info(f"Open: file://{output_path.absolute()}")
        else:
            echo_error("This graph object does not support HTML export.")

    elif output_path.suffix == ".dot":
        if hasattr(g_wrapper, "to_dot"):
            dot_content = g_wrapper.to_dot()
            output_path.write_text(dot_content)
            echo_success(f"Generated: {output_path}")
            echo_info(f"Render with: dot -Tpng {output_path} -o graph.png")
        else:
             echo_error("This graph object does not support DOT export.")

    else:
        echo_error(f"Unsupported format: {output_path.suffix}")
        click.echo("Supported: .html, .dot")