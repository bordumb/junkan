"""
Blast Radius Command - Calculate downstream impact.

Fixed to ensure consistent semantic impact analysis regardless of storage backend.
Prioritizes hydrating the Graph model to leverage bidirectional edge traversal.
"""

import json
import logging
from typing import Any

import click

from ...analysis.blast_radius import BlastRadiusAnalyzer
from ..formatting import format_blast_radius
from ..utils import echo_error, load_graph

logger = logging.getLogger(__name__)


@click.command("blast-radius")
@click.argument("artifacts", nargs=-1)
@click.option("-d", "--db", "db_path", default=".jnkn/jnkn.db",
            help="Path to Junkan database or graph.json")
@click.option("--max-depth", default=-1, type=int,
              help="Maximum traversal depth (-1 for unlimited)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def blast_radius(artifacts: tuple, db_path: str, max_depth: int, as_json: bool) -> None:
    """
    Calculate downstream impact for changed artifacts.
    """
    if not artifacts:
        echo_error("Provide at least one artifact to analyze")
        click.echo("Examples:")
        click.echo("  jnkn blast env:DB_HOST")
        return

    # 1. Load the unified graph model
    graph = load_graph(db_path)
    
    if graph is None:
        return

    # 2. Resolve inputs to actual Node IDs
    resolved_artifacts = []
    for artifact in artifacts:
        resolved_id = _resolve_node_id(graph, artifact)
        if resolved_id:
            resolved_artifacts.append(resolved_id)
        else:
            echo_error(f"Artifact not found: {artifact}")

    if not resolved_artifacts:
        return

    # 3. Run Analysis
    analyzer = BlastRadiusAnalyzer(graph=graph)
    result = analyzer.calculate(resolved_artifacts, max_depth=max_depth)

    # 4. Output
    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(format_blast_radius(result))


def _resolve_node_id(graph: Any, input_id: str) -> str | None:
    """
    Intelligently resolve user input to a Node ID.
    """
    # 1. Exact match
    if graph.has_node(input_id):
        return input_id

    # 2. Terraform Output Heuristic
    # Handle 'infra:name' -> 'infra:output:name'
    if input_id.startswith("infra:") and "output" not in input_id:
        candidate = input_id.replace("infra:", "infra:output:")
        if graph.has_node(candidate):
            return candidate
            
    # 3. Terraform Resource Dot Notation Heuristic
    # Handle 'infra:aws_db_instance.main' -> 'infra:aws_db_instance:main'
    if input_id.startswith("infra:") and "." in input_id:
        candidate = input_id.replace(".", ":")
        if graph.has_node(candidate):
            return candidate

    # 4. Prefix Heuristics
    prefixes = ["env:", "file://", "infra:", "data:", "k8s:"]
    for prefix in prefixes:
        if not input_id.startswith(prefix):
            candidate = f"{prefix}{input_id}"
            if graph.has_node(candidate):
                return candidate

    # 5. Fuzzy Search (Substring)
    matches = graph.find_nodes(input_id)
    if matches:
        # Prefer exact suffix match (e.g. input="app.py" matches "file://.../src/app.py")
        for m in matches:
            if m.endswith(input_id) or f"/{input_id}" in m:
                return m
        return matches[0]

    return None
