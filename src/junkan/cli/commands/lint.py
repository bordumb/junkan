"""
Lint Command - Find issues in the lineage graph.

Checks for orphan nodes, circular dependencies, and other problems.
"""

import click
from pathlib import Path

from ..utils import echo_success, echo_error, load_graph


@click.command()
@click.option("-g", "--graph", "graph_file", default=".",
              help="Path to graph JSON file")
def lint(graph_file: str):
    """
    Find issues in the lineage graph.
    
    \b
    Checks for:
      - Orphan nodes (no connections)
      - Circular dependencies
      - Missing dependencies
    
    \b
    Examples:
        jnkn lint
        jnkn lint -g custom-graph.json
    """
    graph = load_graph(graph_file)
    if graph is None:
        return
    
    click.echo()
    click.echo(f"🔍 {click.style('Lineage Lint', bold=True)}")
    click.echo("═" * 60)
    
    issues = 0
    
    # Check for orphans
    orphans = graph.find_orphans()
    if orphans:
        click.echo()
        click.echo(click.style(f"⚠️  Orphan Nodes ({len(orphans)} found)", fg="yellow"))
        click.echo(click.style("   Nodes with no connections", dim=True))
        for node_id in orphans[:10]:
            click.echo(f"   • {node_id}")
        if len(orphans) > 10:
            click.echo(f"   ... and {len(orphans) - 10} more")
        issues += len(orphans)
    
    # Check for cycles
    cycles = graph.find_cycles()
    if cycles:
        click.echo()
        click.echo(click.style(f"🔄 Cycles Detected ({len(cycles)} found)", fg="red"))
        click.echo(click.style("   Circular dependencies", dim=True))
        for cycle in cycles[:5]:
            cycle_str = " → ".join(cycle[:5])
            if len(cycle) > 5:
                cycle_str += " → ..."
            click.echo(f"   • {cycle_str}")
        if len(cycles) > 5:
            click.echo(f"   ... and {len(cycles) - 5} more")
        issues += len(cycles)
    
    # Print statistics
    stats = graph.stats()
    click.echo()
    click.echo(click.style("📊 Statistics", fg="cyan"))
    click.echo(f"   Total nodes: {stats['total_nodes']}")
    click.echo(f"   Total edges: {stats['total_edges']}")
    
    if stats.get("nodes_by_type"):
        click.echo("   By type:")
        for node_type, count in stats["nodes_by_type"].items():
            click.echo(f"     {node_type}: {count}")
    
    # Summary
    click.echo()
    if issues == 0:
        echo_success("No issues found")
    else:
        click.echo(click.style(f"Found {issues} issue(s)", fg="yellow"))
    
    return 0 if issues == 0 else 1