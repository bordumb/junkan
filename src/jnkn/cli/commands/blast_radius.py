"""
Blast Radius Command - Calculate downstream impact.

Standardized output version.
"""

import logging
from typing import Any, Dict, List

import click
from pydantic import BaseModel, Field

from ...analysis.blast_radius import BlastRadiusAnalyzer
from ...core.exceptions import GraphNotFoundError, NodeNotFoundError
from ..formatting import format_blast_radius
from ..renderers import JsonRenderer
from ..utils import echo_error, load_graph

logger = logging.getLogger(__name__)


# --- API Models ---
class BlastRadiusResponse(BaseModel):
    source_artifacts: List[str]
    impacted_artifacts: List[str]
    count: int
    breakdown: Dict[str, List[str]] = Field(default_factory=dict)


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
    renderer = JsonRenderer("blast-radius")

    if not as_json:
        # Legacy/Human Text Mode
        _run_human_mode(artifacts, db_path, max_depth)
        return

    # JSON Mode (Strict Contract)
    error_to_report = None
    response_data = None

    with renderer.capture():
        try:
            if not artifacts:
                raise ValueError("Provide at least one artifact to analyze")

            graph = load_graph(db_path)
            if graph is None:
                raise GraphNotFoundError(db_path)

            resolved_artifacts = []
            for artifact in artifacts:
                resolved_id = _resolve_node_id(graph, artifact)
                if resolved_id:
                    resolved_artifacts.append(resolved_id)
                else:
                    raise NodeNotFoundError(artifact)

            analyzer = BlastRadiusAnalyzer(graph=graph)
            raw_result = analyzer.calculate(resolved_artifacts, max_depth=max_depth)

            # Map to API Model
            response_data = BlastRadiusResponse(
                source_artifacts=raw_result["source_artifacts"],
                impacted_artifacts=raw_result["impacted_artifacts"],
                count=raw_result["count"],
                # Assuming raw_result includes breakdown or we compute it here.
                # For safety against legacy return types, providing default.
                breakdown=raw_result.get("breakdown", {})
            )
            
        except Exception as e:
            error_to_report = e

    # Outside capture context, so print() works
    if error_to_report:
        renderer.render_error(error_to_report)
    elif response_data:
        renderer.render_success(response_data)


def _run_human_mode(artifacts, db_path, max_depth):
    """Legacy text logic."""
    if not artifacts:
        echo_error("Provide at least one artifact to analyze")
        return

    graph = load_graph(db_path)
    if graph is None:
        return

    resolved_artifacts = []
    for artifact in artifacts:
        resolved_id = _resolve_node_id(graph, artifact)
        if resolved_id:
            resolved_artifacts.append(resolved_id)
        else:
            echo_error(f"Artifact not found: {artifact}")

    if not resolved_artifacts:
        return

    analyzer = BlastRadiusAnalyzer(graph=graph)
    result = analyzer.calculate(resolved_artifacts, max_depth=max_depth)
    click.echo(format_blast_radius(result))


def _resolve_node_id(graph: Any, input_id: str) -> str | None:
    # 1. Exact match
    if graph.has_node(input_id):
        return input_id

    # 2. Terraform Output Heuristic
    if input_id.startswith("infra:") and "output" not in input_id:
        candidate = input_id.replace("infra:", "infra:output:")
        if graph.has_node(candidate):
            return candidate
            
    # 3. Terraform Resource Dot Notation Heuristic
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
        for m in matches:
            if m.endswith(input_id) or f"/{input_id}" in m:
                return m
        return matches[0]

    return None
