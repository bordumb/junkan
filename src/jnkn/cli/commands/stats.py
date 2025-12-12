"""
Stats and Clear Commands - Graph statistics and cleanup.
"""

import json
from pathlib import Path

import click

from ..utils import echo_error, echo_success, load_graph


@click.command()
@click.option("-g", "--graph", "graph_file", default=".", help="Path to graph JSON file")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stats(graph_file: str, as_json: bool):
    """
    Show graph statistics.
    Displays node counts, edge counts, and breakdowns by type.

    \b
    Examples:
        jnkn stats
        jnkn stats --json
    """
    graph_path = Path(graph_file)

    if not graph_path.exists():
        echo_error(f"Graph not found: {graph_file}")
        click.echo("Run 'jnkn scan' first to create the graph.")
        return

    graph = load_graph(graph_file)
    if graph is None:
        return

    s = graph.stats() if hasattr(graph, "stats") else graph.get_stats()

    if as_json:
        click.echo(json.dumps(s, indent=2))
        return

    click.echo()
    click.echo(f"📊 {click.style('Graph Statistics', bold=True)}")
    click.echo("═" * 40)
    click.echo()

    # NEW: Display Backend (This proves we are on rustworkx)
    backend = s.get("backend", "unknown")
    backend_color = "green" if backend == "rustworkx" else "yellow"
    click.echo(f"Backend: {click.style(backend, fg=backend_color, bold=True)}")

    click.echo(f"Source: {graph_file}")
    click.echo(f"Size: {graph_path.stat().st_size / 1024:.1f} KB")
    click.echo()
    click.echo(f"Nodes: {s['total_nodes']}")
    click.echo(f"Edges: {s['total_edges']}")

    # NEW: Show token index stats if available
    if "indexed_tokens" in s:
        click.echo(f"Indexed Tokens: {s['indexed_tokens']}")

    if s.get("nodes_by_type"):
        click.echo()
        click.echo("Nodes by type:")
        for node_type, count in s["nodes_by_type"].items():
            click.echo(f"  {node_type}: {count}")

    if s.get("edges_by_type"):
        click.echo()
        click.echo("Edges by type:")
        for edge_type, count in s["edges_by_type"].items():
            click.echo(f"  {edge_type}: {count}")

    if "orphans" in s:
        click.echo()
        click.echo(f"Orphans: {s['orphans']}")

    click.echo()


@click.command()
@click.option("-g", "--graph", "graph_file", default=".", help="Path to graph JSON file")
@click.option("--all", "clear_all", is_flag=True, help="Clear all .jnkn data")
@click.confirmation_option(prompt="Are you sure you want to clear the data?")
def clear(graph_file: str, clear_all: bool):
    """
    Clear graph data.
    \b
    Examples:
        jnkn clear
        jnkn clear --all
    """
    cleared = []

    if clear_all:
        jnkn_dir = Path(".jnkn")
        if jnkn_dir.exists():
            import shutil

            shutil.rmtree(jnkn_dir)
            cleared.append(".jnkn/")
    else:
        graph_path = Path(graph_file)
        if graph_path.exists():
            graph_path.unlink()
            cleared.append(graph_file)

    if cleared:
        echo_success(f"Cleared: {', '.join(cleared)}")
    else:
        click.echo("Nothing to clear.")
