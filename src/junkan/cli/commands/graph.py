"""
Graph Command - Generate interactive visualization.

Creates an HTML file with an interactive graph using vis.js.
"""

import click
from pathlib import Path

from ..utils import echo_success, echo_error, echo_info, load_graph


@click.command()
@click.option("-i", "--input", "graph_file", default=".",
              help="Input graph JSON file")
@click.option("-o", "--output", default="lineage.html",
              help="Output file (.html or .dot)")
def graph(graph_file: str, output: str):
    """
    Generate interactive visualization.
    
    Creates an HTML file with a zoomable, searchable graph view.
    Click on nodes to see their upstream/downstream dependencies.
    
    \b
    Examples:
        jnkn graph
        jnkn graph -o my-pipeline.html
        jnkn graph -i custom.json -o viz.html
    """
    g = load_graph(graph_file)
    if g is None:
        return
    
    output_path = Path(output)
    
    if output_path.suffix == ".html":
        g.export_html(output_path)
        echo_success(f"Generated: {output_path}")
        echo_info(f"Open: file://{output_path.absolute()}")
    
    elif output_path.suffix == ".dot":
        dot_content = g.to_dot()
        output_path.write_text(dot_content)
        echo_success(f"Generated: {output_path}")
        echo_info(f"Render with: dot -Tpng {output_path} -o graph.png")
    
    else:
        echo_error(f"Unsupported format: {output_path.suffix}")
        click.echo("Supported: .html, .dot")
        