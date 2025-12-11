"""
Scan Command - Parse codebase and build dependency graph.
Standardized output version.
"""

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List

import click
from pydantic import BaseModel

from ...core.graph import DependencyGraph
from ...core.stitching import Stitcher
from ...core.storage.sqlite import SQLiteStorage
from ...core.types import Edge, Node
from ...parsing.base import ParserContext
from ...parsing.python.parser import PythonParser
from ...parsing.terraform.parser import TerraformParser
from ..renderers import JsonRenderer
from ..utils import SKIP_DIRS, echo_error, echo_low_node_warning, echo_success

logger = logging.getLogger(__name__)

# --- API Models ---
class ScanSummary(BaseModel):
    """
    Structured response for the scan command.
    """
    total_files: int
    files_parsed: int
    files_skipped: int
    nodes_found: int
    edges_found: int
    new_links_stitched: int
    output_path: str
    duration_sec: float


class _null_context:
    """Helper for non-capture mode."""
    def __enter__(self): pass
    def __exit__(self, *args): pass


@click.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output file (.db or .json)")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
@click.option("--no-recursive", is_flag=True, help="Don't scan subdirectories")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def scan(directory: str, output: str, verbose: bool, no_recursive: bool, as_json: bool):
    """
    Scan directory and build dependency graph.
    """
    scan_path = Path(directory).absolute()
    renderer = JsonRenderer("scan")
    start_time = time.time()

    # Capture context for JSON mode, null context otherwise
    context_manager = renderer.capture() if as_json else _null_context()
    
    error_to_report = None
    response_data = None

    with context_manager:
        try:
            if not as_json:
                click.echo(f"🔍 Scanning {scan_path}")

            # 1. Initialize Parsers
            parsers = _load_parsers(scan_path, verbose)
            
            if not parsers:
                if not as_json:
                    echo_error("No parsers available. Check your installation.")
                # We return early here to match legacy behavior/tests
                return

            # 2. Discover Files
            extensions = {".py", ".tf", ".js", ".ts", ".jsx", ".tsx", ".yml", ".yaml", ".json"}
            if no_recursive:
                files = [f for f in scan_path.glob("*") if f.suffix in extensions and f.is_file()]
            else:
                files = [f for f in scan_path.rglob("*") if f.suffix in extensions and f.is_file()]

            files = [f for f in files if not any(d in f.parts for d in SKIP_DIRS)]
            
            if not as_json:
                click.echo(f"   Files found: {len(files)}")

            # 3. Parse Files
            graph = DependencyGraph()
            
            # Iterator wrapper to handle progress bar vs silent
            if not as_json:
                with click.progressbar(files, label="   Parsing files", show_pos=True) as bar:
                    for file_path in bar:
                        _process_file(file_path, parsers, graph, verbose)
            else:
                for file_path in files:
                    _process_file(file_path, parsers, graph, verbose)

            # 4. Stitching
            stitched_count = 0
            if graph.node_count > 0:
                if not as_json:
                    click.echo("🧵 Stitching cross-domain dependencies...")
                stitcher = Stitcher()
                stitched_edges = stitcher.stitch(graph)
                stitched_count = len(stitched_edges)
                if not as_json:
                    click.echo(f"   Created {stitched_count} new links")

            # 5. Output warnings (Text mode only)
            if not as_json and graph.node_count < 5 and len(files) > 0:
                echo_low_node_warning(graph.node_count)
            elif not as_json:
                echo_success("Scan complete")
                click.echo(f"   Nodes: {graph.node_count}")
                click.echo(f"   Edges: {graph.edge_count}")

            # 6. Save Output
            if output:
                output_path = Path(output)
            else:
                output_path = Path(".jnkn/jnkn.db")
            
            _save_output(graph, output_path, verbose)

            # Prepare API Response
            duration = time.time() - start_time
            response_data = ScanSummary(
                total_files=len(files),
                files_parsed=len(files), # Simplified stats
                files_skipped=0,
                nodes_found=graph.node_count,
                edges_found=graph.edge_count,
                new_links_stitched=stitched_count,
                output_path=str(output_path),
                duration_sec=round(duration, 2)
            )

        except Exception as e:
            error_to_report = e

    # Render output outside capture
    if as_json:
        if error_to_report:
            renderer.render_error(error_to_report)
        elif response_data:
            renderer.render_success(response_data)


def _process_file(file_path, parsers, graph, verbose):
    nodes, edges = _parse_file(file_path, parsers, verbose)
    for node in nodes:
        graph.add_node(node)
    for edge in edges:
        graph.add_edge(edge)


def _load_parsers(root_dir: Path, verbose: bool = False) -> Dict[str, Any]:
    parsers = {}
    context = ParserContext(root_dir=root_dir)
    parsers["python"] = PythonParser(context)
    parsers["terraform"] = TerraformParser(context)
    return parsers


def _parse_file(file_path: Path, parsers: Dict[str, Any], verbose: bool) -> tuple[List[Node], List[Edge]]:
    nodes: List[Node] = []
    edges: List[Edge] = []
    try:
        content = file_path.read_bytes()
    except Exception:
        return nodes, edges

    for parser_name, parser in parsers.items():
        try:
            if not parser.can_parse(file_path): continue
            results = parser.parse(file_path, content)
            for item in results:
                if isinstance(item, Edge): edges.append(item)
                elif isinstance(item, Node): nodes.append(item)
        except Exception:
            pass
            
    return nodes, edges


def _save_output(graph: DependencyGraph, output_path: Path, verbose: bool) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix == ".json":
        output_path.write_text(json.dumps(graph.to_dict(), indent=2, default=str))
    elif output_path.suffix == ".db":
        storage = SQLiteStorage(output_path)
        storage.clear()
        nodes = [node for node in graph.iter_nodes()]
        storage.save_nodes_batch(nodes)
        edges = [edge for edge in graph.iter_edges()]
        storage.save_edges_batch(edges)
        storage.close()
    else:
        # Restore fallback error for unknown extensions
        echo_error(f"Unknown format: {output_path.suffix}")
