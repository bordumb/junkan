"""
Blast Radius Command - Calculate downstream impact.

Wraps the BlastRadiusAnalyzer for CLI access.
"""

import click
import json
from pathlib import Path

from ..utils import echo_error, echo_info, load_graph


@click.command("blast-radius")
@click.argument("artifacts", nargs=-1)
@click.option("-g", "--graph", "graph_file", default=".",
              help="Path to graph JSON file")
@click.option("--max-depth", default=-1, type=int,
              help="Maximum traversal depth (-1 for unlimited)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def blast_radius(artifacts: tuple, graph_file: str, max_depth: int, as_json: bool):
    """
    Calculate downstream impact for changed artifacts.
    
    \b
    Examples:
        jnkn blast env:DB_HOST
        jnkn blast warehouse.dim_users
        jnkn blast src/models.py infra:payment_db
    """
    if not artifacts:
        echo_error("Provide at least one artifact to analyze")
        click.echo()
        click.echo("Examples:")
        click.echo("  jnkn blast env:DB_HOST")
        click.echo("  jnkn blast warehouse.dim_users")
        return
    
    # Try to use BlastRadiusAnalyzer if available
    try:
        from ...analysis.blast_radius import BlastRadiusAnalyzer
        from ...core.graph import DependencyGraph
        
        # Load graph data
        graph_path = Path(graph_file)
        if graph_path.exists():
            data = json.loads(graph_path.read_text())
            graph = DependencyGraph()
            # Load nodes and edges...
            analyzer = BlastRadiusAnalyzer(graph=graph)
            result = analyzer.calculate(list(artifacts), max_depth=max_depth)
            
            if as_json:
                click.echo(json.dumps(result, indent=2))
            else:
                _print_result(result)
            return
    except ImportError:
        pass
    
    # Fallback: use LineageGraph
    graph = load_graph(graph_file)
    if graph is None:
        return
    
    all_downstream = set()
    resolved_artifacts = []
    
    for artifact in artifacts:
        # Resolve partial names
        if not artifact.startswith(("data:", "file:", "job:", "env:", "infra:")):
            matches = graph.find_nodes(artifact)
            if matches:
                artifact = matches[0]
            else:
                echo_error(f"No match found for: {artifact}")
                continue
        
        resolved_artifacts.append(artifact)
        downstream = graph.downstream(artifact, max_depth)
        all_downstream.update(downstream)
    
    result = {
        "source_artifacts": resolved_artifacts,
        "total_impacted_count": len(all_downstream),
        "impacted_artifacts": sorted(all_downstream),
        "breakdown": _categorize(all_downstream),
    }
    
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        _print_result(result)


def _categorize(artifacts: set) -> dict:
    """Categorize artifacts by type."""
    breakdown = {
        "data": [],
        "code": [],
        "config": [],
        "infra": [],
        "other": [],
    }
    
    for art in artifacts:
        if art.startswith("data:"):
            breakdown["data"].append(art)
        elif art.startswith(("file:", "job:")):
            breakdown["code"].append(art)
        elif art.startswith("env:"):
            breakdown["config"].append(art)
        elif art.startswith("infra:"):
            breakdown["infra"].append(art)
        else:
            breakdown["other"].append(art)
    
    return breakdown


def _print_result(result: dict):
    """Pretty print blast radius result."""
    click.echo()
    click.echo(f"💥 {click.style('Blast Radius Analysis', bold=True)}")
    click.echo("═" * 60)
    
    click.echo()
    click.echo(click.style("Source artifacts:", bold=True))
    for art in result.get("source_artifacts", []):
        click.echo(f"  • {art}")
    
    click.echo()
    total = result.get("total_impacted_count", 0)
    click.echo(f"{click.style('Total impacted:', bold=True)} {total} artifacts")
    
    breakdown = result.get("breakdown", {})
    if breakdown:
        click.echo()
        click.echo(click.style("By category:", bold=True))
        for category, items in breakdown.items():
            if items:
                click.echo(f"  {category}: {len(items)}")
    
    click.echo()
    click.echo(click.style("Impacted artifacts:", bold=True))
    for art in result.get("impacted_artifacts", [])[:20]:
        click.echo(f"  • {art}")
    
    if total > 20:
        click.echo(f"  ... and {total - 20} more")
    
    click.echo()