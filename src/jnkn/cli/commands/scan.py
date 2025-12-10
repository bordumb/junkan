"""
Scan Command - Parse codebase and build dependency graph.

Scans directories for supported file types and extracts:
- PySpark table reads/writes
- Environment variables
- Terraform resources
- spark.yml job configurations
"""

from pathlib import Path
from typing import Any, Dict, List, Set

import click

from ..utils import SKIP_DIRS, echo_error, echo_info, echo_low_node_warning, echo_success


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
    from ...graph.lineage import LineageGraph

    scan_path = Path(directory).absolute()
    click.echo(f"🔍 Scanning {scan_path}")

    # Initialize parsers
    parsers = _load_parsers(scan_path)

    if not parsers:
        echo_error("No parsers available. Install with: pip install jnkn[full]")
        return

    if verbose:
        click.echo(f"   Parsers: {', '.join(parsers.keys())}")

    # Find files
    extensions = {".py", ".tf", ".yml", ".yaml", ".json"}
    if no_recursive:
        files = [f for f in scan_path.glob("*") if f.suffix in extensions and f.is_file()]
    else:
        files = [f for f in scan_path.rglob("*") if f.suffix in extensions and f.is_file()]

    # Filter out skip directories
    files = [f for f in files if not any(d in f.parts for d in SKIP_DIRS)]

    click.echo(f"   Files found: {len(files)}")

    # Parse files
    graph = LineageGraph()
    all_nodes: List[Dict[str, Any]] = []
    all_edges: List[Dict[str, Any]] = []

    for file_path in files:
        nodes, edges = _parse_file(file_path, parsers, verbose)
        all_nodes.extend(nodes)
        all_edges.extend(edges)

    # Deduplicate nodes
    seen_ids: Set[str] = set()
    unique_nodes = []
    for node in all_nodes:
        node_id = node.get("id", "")
        if node_id and node_id not in seen_ids:
            seen_ids.add(node_id)
            unique_nodes.append(node)

    graph.load_from_dict({"nodes": unique_nodes, "edges": all_edges})

    # Output results
    stats = graph.stats()
    
    # NEW: Check for low node count "panic state"
    total_nodes = stats.get('total_nodes', 0)
    if total_nodes < 5:
        echo_low_node_warning(total_nodes)
    else:
        echo_success("Scan complete")
        click.echo(f"   Nodes: {total_nodes}")
        click.echo(f"   Edges: {stats.get('total_edges', 0)}")

    # Save output
    if output:
        output_path = Path(output)
        _save_output(graph, output_path)
    else:
        # Default output
        default_path = Path(".jnkn/lineage.json")
        default_path.parent.mkdir(parents=True, exist_ok=True)
        default_path.write_text(graph.to_json())
        echo_info(f"Saved: {default_path}")


def _load_parsers(root_dir: Path) -> Dict[str, Any]:
    """Load available parsers."""
    parsers = {}

    try:
        from ...parsing.base import ParserContext
        context = ParserContext(root_dir=root_dir)
    except ImportError:
        context = None

    parser_modules = [
        ("pyspark", "...parsing.pyspark.parser", "PySparkParser"),
        ("python", "...parsing.python.parser", "PythonParser"),
        ("spark_yaml", "...parsing.spark_yaml.parser", "SparkYamlParser"),
        ("terraform", "...parsing.terraform.parser", "TerraformParser"),
    ]

    for name, module_path, class_name in parser_modules:
        try:
            import importlib
            # Resolve relative import
            module = importlib.import_module(module_path, package=__name__)
            parser_class = getattr(module, class_name)
            parsers[name] = parser_class(context)
        except (ImportError, AttributeError):
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
                item_dict = _to_dict(item)
                if "source_id" in item_dict:
                    edges.append(item_dict)
                else:
                    nodes.append(item_dict)
        except Exception as e:
            if verbose:
                click.echo(f"   ✗ {parser_name} error: {e}", err=True)

    return nodes, edges


def _to_dict(item: Any) -> Dict[str, Any]:
    """Convert parser output to dictionary."""
    if hasattr(item, "model_dump"):
        return item.model_dump()
    elif hasattr(item, "__dict__"):
        return {k: v for k, v in item.__dict__.items() if not k.startswith("_")}
    return {}


def _save_output(graph, output_path: Path) -> None:
    """Save graph to output file."""
    from ..utils import echo_info, echo_success

    if output_path.suffix == ".json":
        output_path.write_text(graph.to_json())
        echo_success(f"Saved: {output_path}")
    elif output_path.suffix == ".html":
        graph.export_html(output_path)
        echo_success(f"Saved: {output_path}")
        echo_info(f"Open: file://{output_path.absolute()}")
    else:
        click.echo(f"Unknown format: {output_path.suffix}", err=True)
