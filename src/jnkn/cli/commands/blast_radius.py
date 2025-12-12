"""
Blast Radius Command - Calculate downstream impact.

Refactored to use strict Pydantic models for JSON output API contract.
Restored heuristic node resolution logic to fix tests.
"""

import logging
from typing import Any

import click

from ...analysis.blast_radius import BlastRadiusAnalyzer
from ...core.api.models import BlastRadiusResponse, BreakdownStats
from ...core.exceptions import GraphNotFoundError, NodeNotFoundError
from ..formatting import format_blast_radius
from ..renderers import JsonRenderer
from ..utils import echo_error, load_graph

logger = logging.getLogger(__name__)


@click.command("blast-radius")
@click.argument("artifacts", nargs=-1)
@click.option(
    "-d", "--db", "db_path", default=".jnkn/jnkn.db", help="Path to Junkan database or graph.json"
)
@click.option(
    "--max-depth", default=-1, type=int, help="Maximum traversal depth (-1 for unlimited)"
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def blast_radius(artifacts: tuple, db_path: str, max_depth: int, as_json: bool) -> None:
    """
    Calculate downstream impact for changed artifacts.
    """
    renderer = JsonRenderer("blast-radius")

    # If NOT json, we run legacy human mode immediately and return.
    # This prevents the JsonRenderer capture context from swallowing text output.
    if not as_json:
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

            # Map to Strict API Model
            breakdown_dict = raw_result.get("breakdown", {})

            response_data = BlastRadiusResponse(
                source_artifacts=raw_result["source_artifacts"],
                impacted_artifacts=raw_result["impacted_artifacts"],
                count=raw_result["count"],
                breakdown=BreakdownStats(
                    code=breakdown_dict.get("code", []),
                    infra=breakdown_dict.get("infra", []),
                    data=breakdown_dict.get("data", []),
                    config=breakdown_dict.get("config", []),
                    other=breakdown_dict.get("other", []),
                ),
            )

        except Exception as e:
            error_to_report = e

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
    """
    Resolve fuzzy artifact names to concrete Node IDs.
    Restored full heuristics for Terraform and partial matches.
    """
    # 1. Exact match
    if graph.has_node(input_id):
        return input_id

    # 2. Terraform Output Heuristic (infra:output.name -> infra:output:name)
    if input_id.startswith("infra:") and "output" in input_id and "." in input_id:
        candidate = input_id.replace(".", ":")
        if graph.has_node(candidate):
            return candidate

    # 3. Terraform Output Heuristic (infra:name -> infra:output:name)
    if input_id.startswith("infra:") and "output" not in input_id:
        candidate = input_id.replace("infra:", "infra:output:")
        if graph.has_node(candidate):
            return candidate

    # 4. Terraform Resource Dot Notation Heuristic (infra:type.name -> infra:type:name)
    if input_id.startswith("infra:") and "." in input_id:
        candidate = input_id.replace(".", ":")
        if graph.has_node(candidate):
            return candidate

    # 5. Prefix Heuristics
    prefixes = ["env:", "file://", "infra:", "data:", "k8s:"]
    for prefix in prefixes:
        if not input_id.startswith(prefix):
            candidate = f"{prefix}{input_id}"
            if graph.has_node(candidate):
                return candidate

    # 6. Fuzzy Search (Substring)
    matches = graph.find_nodes(input_id)
    if matches:
        # Prefer exact suffix match (file extensions) or path match
        for m in matches:
            if m.endswith(input_id) or f"/{input_id}" in m:
                return m
        return matches[0]

    return None
