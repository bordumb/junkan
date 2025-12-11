"""
Scan Command - Parse codebase and build dependency graph.
Standardized output version with Incremental Scanning.
"""

import json
import logging
import sys
from pathlib import Path

import click
from pydantic import BaseModel

from ...core.stitching import Stitcher
from ...core.storage.sqlite import SQLiteStorage
from ...parsing.engine import ScanConfig, create_default_engine
from ..renderers import JsonRenderer
from ..utils import SKIP_DIRS, echo_low_node_warning, echo_success

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
@click.option("-o", "--output", help="Output file (default: .jnkn/jnkn.db)")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
@click.option("--no-recursive", is_flag=True, help="Don't scan subdirectories")
@click.option("--force", is_flag=True, help="Force full rescan (ignore incremental cache)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def scan(
    directory: str, 
    output: str, 
    verbose: bool, 
    no_recursive: bool, 
    force: bool,
    as_json: bool
):
    """
    Scan directory and build dependency graph.
    
    Uses incremental scanning by default: only changed files are re-parsed.
    """
    scan_path = Path(directory).absolute()
    renderer = JsonRenderer("scan")
    
    # 1. Determine Output Path (Persistent DB)
    if output:
        output_path = Path(output)
    else:
        # Default persistent storage
        output_path = Path(".jnkn/jnkn.db")
    
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Capture context for JSON mode, null context otherwise
    context_manager = renderer.capture() if as_json else _null_context()
    
    error_to_report = None
    response_data = None

    with context_manager:
        try:
            if not as_json:
                click.echo(f"🔍 Scanning {scan_path}")
                if output_path.exists() and not force:
                    click.echo("   Using incremental cache")

            # 2. Initialize Engine & Storage
            engine = create_default_engine()
            storage = SQLiteStorage(output_path)
            
            # If force flag is set, clear existing data
            if force:
                storage.clear()

            # 3. Configure Scan
            # Convert user SKIP_DIRS to set
            skip_dirs = SKIP_DIRS.copy()
            if no_recursive:
                # If no recursive, we just rely on engine's discovery which we can't easily restrict 
                # depth on via config yet, but we can hack it or rely on walkers.
                # For now, ScanConfig handles directory skipping.
                pass

            config = ScanConfig(
                root_dir=scan_path,
                skip_dirs=skip_dirs,
                incremental=not force
            )

            # 4. Run Scan (Incremental)
            # Progress callback for text mode
            def progress(path: Path, current: int, total: int):
                if not as_json and verbose:
                    click.echo(f"   [{current}/{total}] checking {path.name}...")

            result = engine.scan_and_store(storage, config, progress_callback=progress)

            if result.is_err():
                # Extract the underlying exception or create a new one
                raise result.unwrap_err().cause or Exception(result.unwrap_err().message)

            stats = result.unwrap()

            if not as_json:
                if stats.files_scanned > 0:
                    click.echo(f"   Parsed {stats.files_scanned} files ({stats.files_unchanged} unchanged)")
                else:
                    click.echo(f"   All {stats.files_unchanged} files up to date")
                
                if stats.files_deleted > 0:
                    click.echo(f"   Pruned {stats.files_deleted} deleted files")

            # 5. Hydrate Graph for Stitching
            # We need the full graph in memory to perform cross-file stitching
            graph = storage.load_graph()

            # 6. Run Stitching
            stitched_count = 0
            if graph.node_count > 0:
                if not as_json:
                    click.echo("🧵 Stitching cross-domain dependencies...")
                
                stitcher = Stitcher()
                stitched_edges = stitcher.stitch(graph)
                
                if stitched_edges:
                    storage.save_edges_batch(stitched_edges)
                    stitched_count = len(stitched_edges)
                
                if not as_json:
                    click.echo(f"   Created {stitched_count} new links")

            # 7. Finalize & Warnings
            if not as_json:
                if graph.node_count < 5 and stats.files_scanned + stats.files_unchanged > 0:
                    echo_low_node_warning(graph.node_count)
                else:
                    echo_success("Scan complete")
                    click.echo(f"   Total Nodes: {graph.node_count}")
                    click.echo(f"   Total Edges: {graph.edge_count}")

            # 8. Handle JSON Export if requested output format was JSON but we used DB for logic
            # If the user specifically asked for a .json file via -o, we should export it now.
            if output_path.suffix == ".json":
                # The user wants the graph dump, not the DB
                # Overwrite the DB file with JSON (a bit awkward if we used it as DB during scan)
                # Better: parse to DB, then export to JSON at the end
                json_content = json.dumps(graph.to_dict(), indent=2, default=str)
                output_path.write_text(json_content)

            # Prepare API Response
            response_data = ScanSummary(
                total_files=stats.files_scanned + stats.files_unchanged,
                files_parsed=stats.files_scanned,
                files_skipped=stats.files_skipped,
                nodes_found=graph.node_count,
                edges_found=graph.edge_count,
                new_links_stitched=stitched_count,
                output_path=str(output_path),
                duration_sec=round(stats.scan_time_ms / 1000, 2)
            )
            
            # Close DB connection
            storage.close()

        except Exception as e:
            error_to_report = e

    # Render output
    if as_json:
        if error_to_report:
            renderer.render_error(error_to_report)
            sys.exit(1)
        elif response_data:
            renderer.render_success(response_data)
    else:
        # Text Mode: Re-raise exception so Click handles it (prints error + exits 1)
        if error_to_report:
            raise error_to_report
