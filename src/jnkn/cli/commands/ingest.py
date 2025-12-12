"""
Ingest Command - Explicitly ingest specific artifact types.

More explicit than 'scan' - allows you to specify exactly which
Terraform plans, dbt manifests, or code directories to process.
"""

import json
import os
from pathlib import Path
from typing import Set

import click

from ..utils import echo_error, echo_info, echo_success

# Skip these directories
SKIP_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "dist",
    "build",
    ".jnkn",
}


@click.command()
@click.option(
    "--tf-plan", type=click.Path(exists=True), help="Path to Terraform plan JSON (tfplan.json)"
)
@click.option("--dbt-manifest", type=click.Path(exists=True), help="Path to dbt manifest.json")
@click.option(
    "--code-dir", type=click.Path(exists=True), help="Directory to scan for application code"
)
@click.option("--output", "-o", default=".jnkn/graph.json", help="Output graph file")
def ingest(tf_plan: str, dbt_manifest: str, code_dir: str, output: str):
    """
    Ingest specific artifacts into dependency graph.

    Unlike 'scan', this command lets you explicitly specify which
    artifacts to process.

    \b
    Examples:
        jnkn ingest --tf-plan plan.json
        jnkn ingest --dbt-manifest target/manifest.json
        jnkn ingest --code-dir ./src
        jnkn ingest --tf-plan plan.json --code-dir ./src -o deps.json
    """
    if not any([tf_plan, dbt_manifest, code_dir]):
        echo_error("Provide at least one of: --tf-plan, --dbt-manifest, --code-dir")
        return

    relationships = []

    # 1. Terraform
    if tf_plan:
        click.echo(f"📦 Ingesting Terraform: {tf_plan}")
        tf_rels = _ingest_terraform(tf_plan)
        relationships.extend(tf_rels)
        click.echo(f"   Found {len(tf_rels)} relationships")

    # 2. dbt
    if dbt_manifest:
        click.echo(f"📦 Ingesting dbt: {dbt_manifest}")
        dbt_rels = _ingest_dbt(dbt_manifest)
        relationships.extend(dbt_rels)
        click.echo(f"   Found {len(dbt_rels)} relationships")

    # 3. Code
    if code_dir:
        click.echo(f"📦 Scanning code: {code_dir}")
        code_rels = _ingest_code(code_dir)
        relationships.extend(code_rels)
        click.echo(f"   Found {len(code_rels)} relationships")

    # Save output
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    result = {
        "nodes": _extract_nodes(relationships),
        "edges": relationships,
        "metadata": {
            "tf_plan": tf_plan,
            "dbt_manifest": dbt_manifest,
            "code_dir": code_dir,
        },
    }

    output_path.write_text(json.dumps(result, indent=2))

    echo_success(f"Ingested {len(relationships)} relationships")
    echo_info(f"Saved: {output_path}")


def _ingest_terraform(plan_path: str) -> list:
    """Ingest Terraform plan."""
    relationships = []

    try:
        from ...parsing.base import ParserContext
        from ...parsing.terraform.parser import TerraformParser

        content = Path(plan_path).read_bytes()
        context = ParserContext()
        parser = TerraformParser(context)

        for item in parser.parse(Path(plan_path), content):
            if hasattr(item, "source_id"):
                relationships.append(
                    {
                        "source_id": item.source_id,
                        "target_id": item.target_id,
                        "type": str(item.type),
                        "source": "terraform",
                    }
                )
    except ImportError:
        # Fallback: basic JSON parsing
        try:
            with open(plan_path) as f:
                plan = json.load(f)

            for change in plan.get("resource_changes", []):
                resource_type = change.get("type", "unknown")
                resource_name = change.get("name", "unknown")
                address = change.get("address", f"{resource_type}.{resource_name}")

                relationships.append(
                    {
                        "source_id": f"infra:{address}",
                        "target_id": f"infra:{resource_type}",
                        "type": "provisions",
                        "source": "terraform",
                    }
                )
        except Exception:
            pass

    return relationships


def _ingest_dbt(manifest_path: str) -> list:
    """Ingest dbt manifest."""
    relationships = []

    try:
        with open(manifest_path) as f:
            manifest = json.load(f)

        # Process nodes (models, sources, etc.)
        for node_id, node in manifest.get("nodes", {}).items():
            for dep in node.get("depends_on", {}).get("nodes", []):
                relationships.append(
                    {
                        "source_id": f"data:{dep}",
                        "target_id": f"data:{node_id}",
                        "type": "transforms",
                        "source": "dbt",
                    }
                )

        # Process sources
        for source_id, source in manifest.get("sources", {}).items():
            relationships.append(
                {
                    "source_id": f"data:{source.get('source_name', 'unknown')}.{source.get('name', 'unknown')}",
                    "target_id": f"data:{source_id}",
                    "type": "provides",
                    "source": "dbt",
                }
            )
    except Exception:
        pass

    return relationships


def _ingest_code(code_dir: str) -> list:
    """Ingest application code."""
    relationships = []
    code_path = Path(code_dir)

    try:
        from ...parsing.base import ParserContext
        from ...parsing.pyspark.parser import PySparkParser
        from ...parsing.python.parser import PythonParser

        context = ParserContext(root_dir=code_path)
        parsers = [PythonParser(context), PySparkParser(context)]
    except ImportError:
        parsers = []

    # Walk directory
    for root, dirs, files in os.walk(code_dir):
        # Skip unwanted directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            file_path = Path(root) / file

            if file_path.suffix not in {".py", ".yml", ".yaml"}:
                continue

            try:
                content = file_path.read_bytes()
                rel_path = file_path.relative_to(code_path)

                for parser in parsers:
                    if not parser.can_parse(file_path, content):
                        continue

                    for item in parser.parse(file_path, content):
                        if hasattr(item, "source_id"):
                            relationships.append(
                                {
                                    "source_id": item.source_id,
                                    "target_id": item.target_id,
                                    "type": str(item.type),
                                    "source": "code_scan",
                                    "file": str(rel_path),
                                }
                            )
            except Exception:
                pass

    return relationships


def _extract_nodes(relationships: list) -> list:
    """Extract unique nodes from relationships."""
    nodes = {}

    for rel in relationships:
        for key in ["source_id", "target_id"]:
            node_id = rel.get(key, "")
            if node_id and node_id not in nodes:
                # Infer type from ID prefix
                if node_id.startswith("data:"):
                    node_type = "data_asset"
                elif node_id.startswith("infra:"):
                    node_type = "infra_resource"
                elif node_id.startswith("env:"):
                    node_type = "env_var"
                elif node_id.startswith("file:"):
                    node_type = "code_file"
                else:
                    node_type = "unknown"

                # Extract name from ID
                name = node_id.split(":", 1)[-1] if ":" in node_id else node_id

                nodes[node_id] = {
                    "id": node_id,
                    "name": name,
                    "type": node_type,
                }

    return list(nodes.values())
