"""
Impact Command - Analyze upstream/downstream dependencies.

Shows what would be affected by changes to a table, file, or resource.
"""

import click
import json
from pathlib import Path

from ..utils import echo_error, load_graph


@click.command()
@click.argument("target")
@click.option("-g", "--graph", "graph_file", default=".",
              help="Path to graph JSON file")
@click.option("--upstream", is_flag=True, help="Show only upstream (sources)")
@click.option("--downstream", is_flag=True, help="Show only downstream (affected)")
@click.option("--max-depth", default=-1, type=int, help="Maximum traversal depth")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def impact(target: str, graph_file: str, upstream: bool, downstream: bool, 
           max_depth: int, as_json: bool):
    """
    Analyze impact of changes to a table or resource.
    
    Shows upstream sources and downstream consumers that would be
    affected by changes.
    
    \b
    Examples:
        jnkn impact warehouse.dim_users
        jnkn impact data:warehouse.fact_events --downstream
        jnkn impact env:DATABASE_HOST --json
    """
    graph = load_graph(graph_file)
    if graph is None:
        return
    
    # Resolve target (support partial matching)
    resolved = _resolve_target(graph, target)
    if resolved is None:
        return
    
    # Calculate impact
    up = graph.upstream(resolved, max_depth) if not downstream else set()
    down = graph.downstream(resolved, max_depth) if not upstream else set()
    
    if as_json:
        click.echo(json.dumps({
            "target": resolved,
            "upstream": sorted(up),
            "downstream": sorted(down),
            "total_affected": len(up) + len(down),
        }, indent=2))
        return
    
    # Pretty print
    _print_impact(graph, resolved, up, down, upstream, downstream)


def _resolve_target(graph, target: str) -> str | None:
    """Resolve partial target name to full node ID."""
    # If already a full ID, use it
    if target.startswith(("data:", "file:", "job:", "env:", "infra:")):
        if target in graph._nodes:
            return target
        echo_error(f"Node not found: {target}")
        return None
    
    # Try partial matching
    matches = graph.find_nodes(target)
    
    if not matches:
        echo_error(f"No node found matching: {target}")
        return None
    
    if len(matches) > 1:
        click.echo(click.style("Multiple matches found:", fg="yellow"))
        for m in matches[:10]:
            click.echo(f"  • {m}")
        if len(matches) > 10:
            click.echo(f"  ... and {len(matches) - 10} more")
        click.echo(f"\nSpecify full ID, e.g.: {matches[0]}")
        return None
    
    return matches[0]


def _print_impact(graph, target: str, up: set, down: set, 
                  show_only_upstream: bool, show_only_downstream: bool):
    """Print formatted impact analysis."""
    node = graph.get_node(target)
    node_name = node.get("name", target) if node else target
    
    click.echo()
    click.echo(f"💥 Impact Analysis: {click.style(node_name, fg='cyan', bold=True)}")
    click.echo("═" * 60)
    
    # Upstream
    if not show_only_downstream:
        click.echo()
        click.echo(click.style(f"⬆️  UPSTREAM ({len(up)} nodes)", fg="yellow"))
        click.echo(click.style("   Sources that feed into this", dim=True))
        
        if up:
            for node_id in sorted(up):
                n = graph.get_node(node_id)
                name = n.get("name", node_id) if n else node_id
                click.echo(f"   • {name}")
        else:
            click.echo(click.style("   (none - this is a source)", dim=True))
    
    # Downstream
    if not show_only_upstream:
        click.echo()
        click.echo(click.style(f"⬇️  DOWNSTREAM ({len(down)} nodes)", fg="green"))
        click.echo(click.style("   Consumers affected by changes", dim=True))
        
        if down:
            for node_id in sorted(down):
                n = graph.get_node(node_id)
                name = n.get("name", node_id) if n else node_id
                click.echo(f"   • {name}")
        else:
            click.echo(click.style("   (none - this is a leaf)", dim=True))
    
    click.echo()
    total = len(up) + len(down)
    click.echo(f"{click.style('Total affected:', bold=True)} {total} nodes")
    click.echo()