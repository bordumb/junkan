"""
Visualize Command - Open interactive graph in browser.
"""

import click
from pathlib import Path

from ..utils import load_graph, echo_error
from ...graph.visualize import open_visualization


@click.command()
@click.option("-g", "--graph", "graph_file", default=".jnkn/jnkn.db",
              help="Path to graph JSON file or DB")
@click.option("-o", "--output", default="graph.html",
              help="Output HTML file path")
def visualize(graph_file: str, output: str) -> None:
    """
    Generate an interactive HTML visualization of the graph.
    
    Opens the result in your default browser.
    """
    graph = load_graph(graph_file)
    
    if graph is None:
        return
        
    if graph.node_count == 0:
        echo_error("Graph is empty. Run 'jnkn scan' first.")
        return

    click.echo(f"🎨 Generating visualization for {graph.node_count} nodes...")
    
    try:
        path = open_visualization(graph, output)
        click.echo(f"✅ Visualization saved to: {path}")
        click.echo("   Opening in browser...")
    except Exception as e:
        echo_error(f"Failed to generate visualization: {e}")