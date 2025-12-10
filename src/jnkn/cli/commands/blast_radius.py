"""
Blast Radius Command - Calculate downstream impact.
"""

import json
import logging
from pathlib import Path
from typing import Optional

import click

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
def blast_radius(artifacts: tuple, db_path: str, max_depth: int, as_json: bool):
    """
    Calculate downstream impact for changed artifacts.
    
    \b
    Examples:
        jnkn blast env:DB_HOST
        jnkn blast infra:output.payment_db_host
        jnkn blast src/models.py infra:payment_db
    """
    if not artifacts:
        echo_error("Provide at least one artifact to analyze")
        click.echo("Examples:")
        click.echo("  jnkn blast env:DB_HOST")
        click.echo("  jnkn blast infra:output.payment_db_host")
        return

    db_file = Path(db_path)
    
    # Handle directory input - look for known files
    if db_file.is_dir():
        if (db_file / "jnkn.db").exists():
            db_file = db_file / "jnkn.db"
        elif (db_file / "lineage.json").exists():
            db_file = db_file / "lineage.json"
        elif (db_file / "graph.json").exists():
            db_file = db_file / "graph.json"
        else:
            db_file = db_file / "jnkn.db"  # Default

    # FALLBACK LOGIC: If default DB is missing, check for lineage.json
    if not db_file.exists():
        if db_path == ".jnkn/jnkn.db" and Path(".jnkn/lineage.json").exists():
             db_file = Path(".jnkn/lineage.json")
        else:
            echo_error(f"Database not found: {db_file}")
            click.echo("Run 'jnkn scan' first to build the dependency graph.")
            return

    # Use SQLite storage for .db files, fallback to JSON for development
    if db_file.suffix == ".db":
        result = _run_with_sqlite(db_file, artifacts, max_depth)
    else:
        result = _run_with_json(db_file, artifacts, max_depth)

    if not result:
        return

    if as_json:
        click.echo(json.dumps(result, indent=2))
    else:
        click.echo(format_blast_radius(result))


def _resolve_artifact_id(graph_source, input_id: str, is_sqlite: bool) -> Optional[str]:
    """
    Intelligently resolve a user input string to a valid graph node ID.
    
    Handles:
    1. Exact matches.
    2. Prefix shortcuts (e.g. 'DB_HOST' -> 'env:DB_HOST').
    3. Separator normalization (e.g. 'infra:output.name' -> 'infra:output:name').
    4. Fuzzy substring matches.

    Args:
        graph_source: Either a LineageGraph (JSON mode) or SQLiteStorage (SQLite mode).
        input_id (str): The user provided artifact string.
        is_sqlite (bool): Flag indicating source type.

    Returns:
        Optional[str]: The resolved node ID, or None.
    """
    
    def check_exists(node_id):
        if is_sqlite:
            return graph_source.load_node(node_id) is not None
        else:
            return graph_source.has_node(node_id)

    # 1. Exact match
    if check_exists(input_id):
        return input_id

    # 2. Heuristic: Separator normalization (Crucial for Terraform outputs)
    # Terraform HCL uses dots (infra:output.name), internal graph uses colons (infra:output:name)
    normalized_id = input_id.replace("infra:output.", "infra:output:")
    if check_exists(normalized_id):
        return normalized_id
    
    # Also try replacing all dots with colons in infra strings
    if input_id.startswith("infra:"):
        colon_id = input_id.replace(".", ":")
        if check_exists(colon_id):
            return colon_id

    # 3. Heuristic: Add prefixes
    prefixes = ["env:", "file://", "infra:", "data:", "k8s:"]
    for prefix in prefixes:
        # Don't double prefix
        if input_id.startswith(prefix): 
            continue
            
        candidate = f"{prefix}{input_id}"
        if check_exists(candidate):
            return candidate
            
    # 4. Fuzzy / Substring Search
    # This is expensive in SQLite, but handled via LIKE if needed.
    # For now, we rely on the specific heuristics above for precision.
    if not is_sqlite:
        # JSON graph has simple find_nodes
        matches = graph_source.find_nodes(input_id)
        if matches:
            # Prefer exact name match within the results
            for m in matches:
                # e.g., if input is "app.py", match "file://.../app.py"
                if m.endswith(input_id) or f"/{input_id}" in m or f":{input_id}" in m:
                    return m
            return matches[0]
            
    return None


def _run_with_sqlite(db_file: Path, artifacts: tuple, max_depth: int) -> dict:
    """Run blast radius using SQLite storage."""
    from ...core.storage.sqlite import SQLiteStorage
    
    storage = SQLiteStorage(db_file)
    
    try:
        all_downstream = set()
        resolved_artifacts = []

        for artifact in artifacts:
            resolved_id = _resolve_artifact_id(storage, artifact, is_sqlite=True)
            
            if not resolved_id:
                echo_error(f"Artifact not found: {artifact}")
                continue
                
            resolved_artifacts.append(resolved_id)
            downstream = storage.query_descendants(resolved_id, max_depth)
            all_downstream.update(downstream)

        return {
            "source_artifacts": resolved_artifacts,
            "total_impacted_count": len(all_downstream),
            "impacted_artifacts": sorted(all_downstream),
            "breakdown": _categorize(all_downstream),
        }
    finally:
        storage.close()


def _run_with_json(graph_path: Path, artifacts: tuple, max_depth: int) -> dict:
    """Run blast radius using JSON graph file (development fallback)."""
    graph = load_graph(str(graph_path))
    if graph is None:
        return {}

    all_downstream = set()
    resolved_artifacts = []

    for artifact in artifacts:
        resolved_id = _resolve_artifact_id(graph, artifact, is_sqlite=False)

        if not resolved_id:
            echo_error(f"No match found for: {artifact}")
            # Try to help user by listing similar nodes if possible
            # (omitted for brevity)
            continue

        resolved_artifacts.append(resolved_id)
        downstream = graph.downstream(resolved_id, max_depth)
        all_downstream.update(downstream)

    return {
        "source_artifacts": resolved_artifacts,
        "total_impacted_count": len(all_downstream),
        "impacted_artifacts": sorted(all_downstream),
        "breakdown": _categorize(all_downstream),
    }


def _categorize(artifacts: set) -> dict:
    """Categorize artifacts by type (Internal use for JSON breakdown)."""
    breakdown = {
        "data": [],
        "code": [],
        "config": [],
        "infra": [],
        "kubernetes": [],
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
        elif art.startswith("k8s:"):
            breakdown["kubernetes"].append(art)
        else:
            breakdown["other"].append(art)

    return breakdown
