"""
Scan Command - Parse codebase and build dependency graph.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import click

from ...core.graph import DependencyGraph
from ...core.stitching import Stitcher
from ...core.storage.sqlite import SQLiteStorage
from ...core.types import Edge, Node
from ...parsing.base import ParserContext
from ..utils import SKIP_DIRS, echo_error, echo_info, echo_low_node_warning, echo_success

# We import these directly to ensure they are available.
# This prevents "No parsers available" errors caused by brittle dynamic discovery.
from ...parsing.python.parser import PythonParser
from ...parsing.terraform.parser import TerraformParser

# We wrap these in try/except blocks so the CLI doesn't crash 
# if specific language dependencies are missing.
try:
    from ...parsing.javascript.parser import JavaScriptParser
except ImportError:
    JavaScriptParser = None

try:
    from ...parsing.kubernetes.parser import KubernetesParser
except ImportError:
    KubernetesParser = None

try:
    from ...parsing.dbt.manifest_parser import DbtManifestParser
except ImportError:
    DbtManifestParser = None

try:
    from ...parsing.pyspark.parser import PySparkParser
except ImportError:
    PySparkParser = None

try:
    from ...parsing.spark_yaml.parser import SparkYamlParser
except ImportError:
    SparkYamlParser = None

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

    # 1. Initialize Parsers
    # We load them explicitly to ensure the registry is populated.
    parsers = _load_parsers(scan_path, verbose)
    
    if not parsers:
        echo_error("No parsers available. Check your installation.")
        return

    # 2. Discover Files
    # We filter by extension early to avoid reading binary files.
    # This set must match the extensions supported by the imported parsers.
    extensions = {".py", ".tf", ".js", ".ts", ".jsx", ".tsx", ".yml", ".yaml", ".json"}
    
    if no_recursive:
        files = [f for f in scan_path.glob("*") if f.suffix in extensions and f.is_file()]
    else:
        files = [f for f in scan_path.rglob("*") if f.suffix in extensions and f.is_file()]

    # Filter out ignored directories (node_modules, venv, etc.)
    files = [f for f in files if not any(d in f.parts for d in SKIP_DIRS)]
    
    # [FIX] Always print file count to satisfy tests and UX
    click.echo(f"   Files found: {len(files)}")

    # 3. Parse Files
    graph = DependencyGraph()
    parsed_node_count = 0

    with click.progressbar(files, label="   Parsing files", show_pos=True) as bar:
        for file_path in bar:
            nodes, edges = _parse_file(file_path, parsers, verbose)
            
            for node in nodes:
                graph.add_node(node)
                parsed_node_count += 1
                
            for edge in edges:
                graph.add_edge(edge)

    # 4. Run Stitching (Cross-Domain Linking)
    if parsed_node_count > 0:
        click.echo("🧵 Stitching cross-domain dependencies...")
        stitcher = Stitcher()
        stitched_edges = stitcher.stitch(graph)
        click.echo(f"   Created {len(stitched_edges)} new links")
    
    # 5. Output Results & Warnings
    if graph.node_count < 5 and len(files) > 0:
        echo_low_node_warning(graph.node_count)
    else:
        echo_success("Scan complete")
        click.echo(f"   Nodes: {graph.node_count}")
        click.echo(f"   Edges: {graph.edge_count}")

    # 6. Save Output
    if output:
        output_path = Path(output)
    else:
        # Default to SQLite DB in .jnkn folder
        output_path = Path(".jnkn/jnkn.db")
    
    _save_output(graph, output_path, verbose)


def _load_parsers(root_dir: Path, verbose: bool = False) -> Dict[str, Any]:
    """
    Explicitly instantiate and register parsers.
    
    This replaces the brittle dynamic import system with explicit registration,
    ensuring that if the package is installed, the parsers work.
    """
    parsers = {}
    context = ParserContext(root_dir=root_dir)

    # Register Core Parsers (Guaranteed to exist)
    parsers["python"] = PythonParser(context)
    parsers["terraform"] = TerraformParser(context)

    # Register Optional Parsers (If imported successfully)
    if JavaScriptParser:
        parsers["javascript"] = JavaScriptParser(context)
    
    if KubernetesParser:
        parsers["kubernetes"] = KubernetesParser(context)
        
    if DbtManifestParser:
        parsers["dbt"] = DbtManifestParser(context)
        
    if PySparkParser:
        parsers["pyspark"] = PySparkParser(context)
        
    if SparkYamlParser:
        parsers["spark_yaml"] = SparkYamlParser(context)

    if verbose:
        click.echo(f"   Loaded parsers: {', '.join(parsers.keys())}")
            
    return parsers


def _parse_file(file_path: Path, parsers: Dict[str, Any], verbose: bool) -> Tuple[List[Node], List[Edge]]:
    """
    Parse a single file using the appropriate parser from the registry.
    """
    nodes: List[Node] = []
    edges: List[Edge] = []
    
    try:
        content = file_path.read_bytes()
    except Exception as e:
        if verbose:
            echo_error(f"Failed to read {file_path}: {e}")
        return nodes, edges

    for parser_name, parser in parsers.items():
        try:
            # Check if this parser handles this file type
            if not parser.can_parse(file_path):
                continue
            
            # Run parsing
            results = parser.parse(file_path, content)
            
            # Sort results into Nodes and Edges
            for item in results:
                if isinstance(item, Edge):
                    edges.append(item)
                elif isinstance(item, Node):
                    nodes.append(item)
                    
        except Exception as e:
            if verbose:
                echo_error(f"Parser error in {file_path} ({parser_name}): {e}")
            pass
            
    return nodes, edges


def _save_output(graph: DependencyGraph, output_path: Path, verbose: bool) -> None:
    """
    Save the graph to disk (SQLite or JSON).
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix == ".json":
        output_path.write_text(json.dumps(graph.to_dict(), indent=2, default=str))
        if verbose:
            echo_info(f"Saved JSON: {output_path}")
            
    elif output_path.suffix == ".db":
        # Initialize Storage Adapter
        storage = SQLiteStorage(output_path)
        
        # Clear existing data to avoid staleness on re-scan
        storage.clear()
        
        # Batch save nodes
        nodes = [node for node in graph.iter_nodes()]
        storage.save_nodes_batch(nodes)
        
        # Batch save edges
        edges = [edge for edge in graph.iter_edges()]
        storage.save_edges_batch(edges)
        
        storage.close()
        
        # Echo clean path relative to CWD
        try:
            rel_path = output_path.relative_to(Path.cwd())
            echo_success(f"Graph saved to {rel_path}")
        except ValueError:
            echo_success(f"Graph saved to {output_path}")
    else:
        # [FIX] Matched error message string to test expectation "Unknown format:"
        echo_error(f"Unknown format: {output_path.suffix}")