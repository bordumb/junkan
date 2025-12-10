"""
Scan Command - Parse codebase and build dependency graph.
"""

import importlib
import logging
from pathlib import Path
from typing import Any, Dict

import click

from ...core.graph import DependencyGraph
from ...core.stitching import Stitcher
from ...core.storage.sqlite import SQLiteStorage
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
@click.option("-o", "--output", help="Output file (.db or .json)")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
@click.option("--no-recursive", is_flag=True, help="Don't scan subdirectories")
def scan(directory: str, output: str, verbose: bool, no_recursive: bool):
    """
    Scan directory and build dependency graph.
    
    Examples:
        jnkn scan
        jnkn scan ./src --output my_graph.db
    """
    scan_path = Path(directory).absolute()
    click.echo(f"🔍 Scanning {scan_path}")

    # Initialize parsers
    parsers = _load_parsers(scan_path, verbose)
    if not parsers:
        echo_error("No parsers available.")
        return

    # Find files
    extensions = {".py", ".tf", ".yml", ".yaml", ".json"}
    if no_recursive:
        files = [f for f in scan_path.glob("*") if f.suffix in extensions and f.is_file()]
    else:
        files = [f for f in scan_path.rglob("*") if f.suffix in extensions and f.is_file()]

    files = [f for f in files if not any(d in f.parts for d in SKIP_DIRS)]
    click.echo(f"   Files found: {len(files)}")

    # Parse files and build graph
    graph = DependencyGraph()
    parsed_node_count = 0

    for file_path in files:
        nodes, edges = _parse_file(file_path, parsers, verbose)
        
        for node in nodes:
            graph.add_node(node)
            parsed_node_count += 1
            
        for edge in edges:
            graph.add_edge(edge)

    # Run Stitching
    if parsed_node_count > 0:
        click.echo("🧵 Stitching cross-domain dependencies...")
        stitcher = Stitcher()
        stitched_edges = stitcher.stitch(graph)
        click.echo(f"   Created {len(stitched_edges)} new links")
    
    # Output results
    if graph.node_count < 5 and len(files) > 0:
        echo_low_node_warning(graph.node_count)
    else:
        echo_success("Scan complete")
        click.echo(f"   Nodes: {graph.node_count}")
        click.echo(f"   Edges: {graph.edge_count}")

    # Save output
    if output:
        output_path = Path(output)
    else:
        # Default to SQLite DB now
        output_path = Path(".jnkn/jnkn.db")
    
    _save_output(graph, output_path, verbose)


def _load_parsers(root_dir: Path, verbose: bool = False) -> Dict[str, Any]:
    """Load available parsers."""
    parsers = {}
    try:
        from ...parsing.base import ParserContext
        context = ParserContext(root_dir=root_dir)
    except ImportError:
        context = None

    for name, module_path, class_name in PARSER_REGISTRY:
        try:
            module = importlib.import_module(module_path)
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
            for item in parser.parse(file_path, content):
                if isinstance(item, Edge):
                    edges.append(item)
                elif isinstance(item, Node):
                    nodes.append(item)
        except Exception:
            pass
    return nodes, edges


def _save_output(graph: DependencyGraph, output_path: Path, verbose: bool) -> None:
    """Save graph to output file (handling both DB and JSON)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix == ".json":
        import json
        output_path.write_text(json.dumps(graph.to_dict(), indent=2, default=str))
        if verbose:
            echo_info(f"Saved JSON: {output_path}")
            
    elif output_path.suffix == ".db":
        # Save to SQLite
        storage = SQLiteStorage(output_path)
        storage.clear() # Overwrite mode
        
        # Batch save nodes
        nodes = [node for node in graph.iter_nodes()]
        storage.save_nodes_batch(nodes)
        
        # Batch save edges
        edges = [edge for edge in graph.iter_edges()]
        storage.save_edges_batch(edges)
        
        storage.close()
        if verbose:
            echo_info(f"Saved Database: {output_path}")
    else:
        echo_error(f"Unknown format: {output_path.suffix}")
