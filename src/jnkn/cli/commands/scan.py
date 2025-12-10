"""
Scan Command - Parse codebase and build dependency graph.

Scans directories for supported file types and extracts:
- PySpark table reads/writes
- Environment variables
- Terraform resources
- spark.yml job configurations
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Dict

import click

from ...core.graph import DependencyGraph
from ...core.stitching import Stitcher
from ...core.types import Edge, Node
from ..utils import SKIP_DIRS, echo_error, echo_info, echo_low_node_warning, echo_success

# Use absolute imports for stability
PARSER_REGISTRY = [
    ("pyspark", "jnkn.parsing.pyspark.parser", "PySparkParser"),
    ("python", "jnkn.parsing.python.parser", "PythonParser"),
    ("spark_yaml", "jnkn.parsing.spark_yaml.parser", "SparkYamlParser"),
    ("terraform", "jnkn.parsing.terraform.parser", "TerraformParser"),
    ("kubernetes", "jnkn.parsing.kubernetes.parser", "KubernetesParser"),
]

logger = logging.getLogger(__name__)


@click.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output file (.json or .html)")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
@click.option("--no-recursive", is_flag=True, help="Don't scan subdirectories")
def scan(directory: str, output: str, verbose: bool, no_recursive: bool):
    """
    Scan directory and build dependency graph.
    
    Parses Python, PySpark, Terraform, and YAML files to extract
    dependencies and data lineage.
    
    \b
    Examples:
        jnkn scan ./src
        jnkn scan ./jobs --output lineage.json
        jnkn scan . -o graph.html -v
    """
    scan_path = Path(directory).absolute()
    click.echo(f"🔍 Scanning {scan_path}")

    # Initialize parsers
    parsers = _load_parsers(scan_path, verbose)

    if not parsers:
        echo_error("No parsers available.")
        click.echo("This usually means dependencies are missing or imports failed.")
        click.echo("Try running with --verbose to see specific import errors.")
        return

    if verbose:
        click.echo(f"   Parsers loaded: {', '.join(parsers.keys())}")

    # Find files
    extensions = {".py", ".tf", ".yml", ".yaml", ".json"}
    if no_recursive:
        files = [f for f in scan_path.glob("*") if f.suffix in extensions and f.is_file()]
    else:
        files = [f for f in scan_path.rglob("*") if f.suffix in extensions and f.is_file()]

    # Filter out skip directories
    files = [f for f in files if not any(d in f.parts for d in SKIP_DIRS)]

    click.echo(f"   Files found: {len(files)}")

    # Parse files and build graph
    graph = DependencyGraph()
    parsed_node_count = 0
    parsed_edge_count = 0

    for file_path in files:
        nodes, edges = _parse_file(file_path, parsers, verbose)
        
        for node in nodes:
            graph.add_node(node)
            parsed_node_count += 1
            
        for edge in edges:
            graph.add_edge(edge)
            parsed_edge_count += 1

    # Run Stitching (The Glue)
    if parsed_node_count > 0:
        click.echo("🧵 Stitching cross-domain dependencies...")
        stitcher = Stitcher()
        stitched_edges = stitcher.stitch(graph)
        click.echo(f"   Created {len(stitched_edges)} new links")
    
    # Output results
    # NEW: Check for low node count "panic state"
    if graph.node_count < 5 and len(files) > 0:
        echo_low_node_warning(graph.node_count)
    else:
        echo_success("Scan complete")
        click.echo(f"   Nodes: {graph.node_count}")
        click.echo(f"   Edges: {graph.edge_count}")

    # Save output
    if output:
        output_path = Path(output)
        _save_output(graph, output_path)
    else:
        # Default output
        default_path = Path(".jnkn/lineage.json")
        default_path.parent.mkdir(parents=True, exist_ok=True)
        # Export using to_dict() which matches the JSON format expected by blast radius
        default_path.write_text(json_dumps(graph.to_dict()))
        if verbose:
            echo_info(f"Saved: {default_path}")


def _load_parsers(root_dir: Path, verbose: bool = False) -> Dict[str, Any]:
    """Load available parsers."""
    parsers = {}

    try:
        from ...parsing.base import ParserContext
        context = ParserContext(root_dir=root_dir)
    except ImportError as e:
        if verbose:
            echo_error(f"Failed to load ParserContext: {e}")
        context = None

    for name, module_path, class_name in PARSER_REGISTRY:
        try:
            module = importlib.import_module(module_path)
            parser_class = getattr(module, class_name)
            parsers[name] = parser_class(context)
        except (ImportError, AttributeError) as e:
            if verbose:
                click.echo(click.style(f"   ⚠️  Failed to load {name}: {e}", fg="yellow"))
            pass

    return parsers


def _parse_file(file_path: Path, parsers: Dict, verbose: bool) -> tuple:
    """Parse a single file with available parsers."""
    nodes = []
    edges = []

    try:
        content = file_path.read_bytes()
    except Exception:
        return nodes, edges

    for parser_name, parser in parsers.items():
        try:
            if not parser.can_parse(file_path, content):
                continue

            if verbose:
                click.echo(f"   → {parser_name}: {file_path.name}")

            for item in parser.parse(file_path, content):
                # Keep items as objects for DependencyGraph
                if isinstance(item, Edge):
                    edges.append(item)
                elif isinstance(item, Node):
                    nodes.append(item)
        except Exception as e:
            if verbose:
                click.echo(f"   ✗ {parser_name} error: {e}", err=True)

    return nodes, edges


def json_dumps(data: Dict) -> str:
    """Helper to dump JSON with datetime handling."""
    import json
    return json.dumps(data, indent=2, default=str)


def _save_output(graph: DependencyGraph, output_path: Path) -> None:
    """Save graph to output file."""
    from ..utils import echo_success

    if output_path.suffix == ".json":
        output_path.write_text(json_dumps(graph.to_dict()))
        echo_success(f"Saved: {output_path}")
    elif output_path.suffix == ".html":
        # Create temporary LineageGraph for HTML export if needed
        # or implement export_html on DependencyGraph.
        # For now, we assume users want JSON or we'd bridge it.
        # Simple fix: warn that HTML needs LineageGraph or update graph.py
        click.echo("HTML export from scan is currently limited to JSON structure.", err=True)
    else:
        click.echo(f"Unknown format: {output_path.suffix}", err=True)
