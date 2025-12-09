"""
Trace Command - Find paths between two nodes.

Useful for understanding how data flows through your pipeline.
"""

import click
from pathlib import Path

from ..utils import echo_error, load_graph


@click.command()
@click.argument("source")
@click.argument("target")
@click.option("-g", "--graph", "graph_file", default=".",
              help="Path to graph JSON file")
@click.option("--max-paths", default=5, help="Maximum paths to show")
def trace(source: str, target: str, graph_file: str, max_paths: int):
    """
    Trace lineage path between two nodes.
    
    Shows how data flows from source to target through your pipeline.
    
    \b
    Examples:
        jnkn trace kafka.raw_events reporting.summary
        jnkn trace data:staging.events data:warehouse.fact_events
    """
    graph = load_graph(graph_file)
    if graph is None:
        return
    
    # Resolve partial names
    source_id = _resolve_node(graph, source, "source")
    if source_id is None:
        return
    
    target_id = _resolve_node(graph, target, "target")
    if target_id is None:
        return
    
    # Find paths
    paths = graph.trace(source_id, target_id)
    
    if not paths:
        click.echo()
        click.echo(click.style("No path found", fg="yellow") + " between:")
        click.echo(f"  Source: {source_id}")
        click.echo(f"  Target: {target_id}")
        return
    
    # Print results
    click.echo()
    click.echo(f"🔗 {click.style('Lineage Trace', bold=True)}")
    click.echo("═" * 60)
    click.echo(f"From: {click.style(source_id, fg='cyan')}")
    click.echo(f"To:   {click.style(target_id, fg='green')}")
    click.echo()
    click.echo(f"{len(paths)} path(s) found:")
    click.echo()
    
    # Sort by length (shortest first)
    sorted_paths = sorted(paths, key=len)[:max_paths]
    
    for i, path in enumerate(sorted_paths, 1):
        click.echo(f"  Path {i}: ({len(path)} steps)")
        for j, node_id in enumerate(path):
            connector = "└─" if j == len(path) - 1 else "├─"
            node = graph.get_node(node_id)
            name = node.get("name", node_id) if node else node_id
            click.echo(f"    {connector} {name}")
        click.echo()
    
    if len(paths) > max_paths:
        click.echo(f"  ... and {len(paths) - max_paths} more paths")


def _resolve_node(graph, name: str, label: str) -> str | None:
    """Resolve partial name to full node ID."""
    if name.startswith(("data:", "file:", "job:", "env:", "infra:")):
        return name
    
    matches = graph.find_nodes(name)
    if not matches:
        echo_error(f"No node found matching {label}: {name}")
        return None
    
    return matches[0]