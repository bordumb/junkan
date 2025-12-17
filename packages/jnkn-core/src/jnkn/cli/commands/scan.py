"""
Scan Command - Parse codebase and build dependency graph.

This command is the primary entry point for analyzing a codebase. It:
1. Resolves dependencies from jnkn.toml (local paths and git remotes)
2. Parses all source files across all repositories
3. Stitches cross-domain connections using fuzzy matching and explicit mappings
4. Stores the resulting graph in SQLite for LSP queries

Supports Discovery and Enforcement modes for different stages of adoption.
"""

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import click
from pydantic import BaseModel
from rich.console import Console

from ...analysis.top_findings import TopFindingsExtractor
from ...core.enhanced_stitching import EnhancedStitcher
from ...core.manifest import ProjectManifest
from ...core.mode import ScanMode, get_mode_manager
from ...core.packs import detect_and_suggest_pack, load_pack
from ...core.resolver import DependencyResolver
from ...core.stitching import Stitcher
from ...core.storage.sqlite import SQLiteStorage
from ...parsing.engine import ScanConfig, create_default_engine
from ..formatters.scan_summary import ScanSummaryFormatter
from ..renderers import JsonRenderer
from ..utils import SKIP_DIRS, echo_low_node_warning

logger = logging.getLogger(__name__)
console = Console()


class ScanSummaryResponse(BaseModel):
    """Structured response for the scan command."""

    total_files: int
    files_parsed: int
    files_skipped: int
    nodes_found: int
    edges_found: int
    new_links_stitched: int
    output_path: str
    duration_sec: float
    mode: str
    pack: Optional[str] = None
    explicit_mappings_applied: int = 0
    repos_scanned: int = 1


class _null_context:
    """Context manager that does nothing (for non-capture mode)."""

    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


def _resolve_scan_targets(
    scan_path: Path,
    no_deps: bool,
    as_json: bool,
    summary_only: bool,
) -> Tuple[List[Tuple[Path, str]], Optional[ProjectManifest]]:
    """
    Resolve all scan targets including dependencies.

    Args:
        scan_path: Primary directory to scan.
        no_deps: If True, skip dependency resolution.
        as_json: If True, suppress console output.
        summary_only: If True, suppress verbose output.

    Returns:
        Tuple of (scan_targets, manifest) where scan_targets is a list of
        (path, repo_name) tuples and manifest is the loaded ProjectManifest.
    """
    manifest = ProjectManifest.load(scan_path / "jnkn.toml")
    scan_targets = [(scan_path, manifest.name)]

    if no_deps:
        return scan_targets, manifest

    try:
        resolver = DependencyResolver(scan_path)
        resolution = resolver.resolve()

        for dep in resolution.dependencies:
            if not as_json and not summary_only:
                # Show dependency source icon
                icon = "📁" if dep.source.value in ("local", "override") else "🌐"
                console.print(f"   {icon} Dependency: [blue]{dep.name}[/blue] ({dep.path})")

            scan_targets.append((dep.path, dep.name))

        # Warn about stale lockfile
        if resolution.lockfile_stale and not as_json:
            console.print("[yellow]⚠️  Lockfile is stale. Run 'jnkn lock' to update.[/yellow]")

    except Exception as e:
        # Don't fail scan if dependency resolution fails, just warn
        logger.warning(f"Dependency resolution failed: {e}")
        if not as_json:
            console.print(f"[yellow]⚠️  Dependency resolution failed: {e}[/yellow]")

    return scan_targets, manifest


def _run_stitching(
    graph,
    manifest: ProjectManifest,
    min_confidence: float,
    active_pack,
    as_json: bool,
    summary_only: bool,
) -> Tuple[int, int, int]:
    """
    Run the stitching process with explicit mapping support.

    Uses EnhancedStitcher if explicit mappings are defined in the manifest,
    otherwise falls back to the basic Stitcher.

    Args:
        graph: The dependency graph to stitch.
        manifest: Project manifest with mappings.
        min_confidence: Minimum confidence threshold.
        active_pack: Framework pack to apply (if any).
        as_json: If True, suppress console output.
        summary_only: If True, suppress verbose output.

    Returns:
        Tuple of (stitched_count, explicit_count, ignored_count).
    """
    stitched_count = 0
    explicit_count = 0
    ignored_count = 0

    if graph.node_count == 0:
        return stitched_count, explicit_count, ignored_count

    if not as_json and not summary_only:
        console.print("🧵 Stitching cross-domain dependencies...")

    # Use EnhancedStitcher if we have explicit mappings
    if manifest.mappings:
        if not as_json and not summary_only:
            console.print(f"   [dim]Applying {len(manifest.mappings)} explicit mapping(s)[/dim]")

        stitcher = EnhancedStitcher(
            mappings=manifest.mappings,
            min_confidence=min_confidence,
        )

        stitch_result = stitcher.stitch(graph)

        stitched_count = stitch_result.total
        explicit_count = stitch_result.explicit_count
        ignored_count = stitch_result.ignored_count

        if not as_json and not summary_only:
            if stitch_result.ignored_count > 0:
                console.print(
                    f"   [dim]Ignored {stitch_result.ignored_count} source(s) (user-defined)[/dim]"
                )
            if stitch_result.filtered_count > 0:
                console.print(
                    f"   [dim]Filtered {stitch_result.filtered_count} low-confidence edge(s)[/dim]"
                )

        return stitched_count, explicit_count, ignored_count, stitch_result.edges

    else:
        # No explicit mappings - use basic Stitcher
        stitcher = Stitcher()

        if active_pack:
            stitcher.apply_pack(active_pack)

        stitched_edges = stitcher.stitch(graph)

        # Filter by confidence threshold
        filtered_edges = [e for e in stitched_edges if (e.confidence or 0.5) >= min_confidence]

        stitched_count = len(filtered_edges)

        return stitched_count, 0, 0, filtered_edges


@click.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-o", "--output", help="Output file (default: .jnkn/jnkn.db)")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed output")
@click.option("--no-recursive", is_flag=True, help="Don't scan subdirectories")
@click.option("--force", is_flag=True, help="Force full rescan (ignore incremental cache)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--mode",
    type=click.Choice(["discovery", "enforcement"]),
    help="Override scan mode (default: auto from config)",
)
@click.option("--pack", "pack_name", help="Use a specific framework pack")
@click.option("--summary-only", is_flag=True, help="Show only summary, not full details")
@click.option("--no-deps", is_flag=True, help="Ignore jnkn.toml dependencies")
@click.option("--frozen", is_flag=True, help="Enforce lockfile versions (fail if stale)")
def scan(
    directory: str,
    output: str,
    verbose: bool,
    no_recursive: bool,
    force: bool,
    as_json: bool,
    mode: Optional[str],
    pack_name: Optional[str],
    summary_only: bool,
    no_deps: bool,
    frozen: bool,
):
    """
    Scan directory and build dependency graph.

    Uses incremental scanning by default: only changed files are re-parsed.
    Automatically resolves and scans dependencies defined in jnkn.toml.

    \b
    Modes:
      discovery    - Show more connections (lower threshold), great for first scan
      enforcement  - Show validated connections only, respect suppressions

    \b
    Examples:
        jnkn scan                           # Scan current directory
        jnkn scan ./src --mode discovery    # Force discovery mode
        jnkn scan --pack django-aws         # Use Django+AWS framework pack
        jnkn scan --no-deps                 # Ignore external dependencies
        jnkn scan --frozen                  # Enforce lockfile versions
    """
    scan_path = Path(directory).absolute()
    renderer = JsonRenderer("scan")

    # =========================================================================
    # 1. Initialize Mode Manager
    # =========================================================================
    mode_manager = get_mode_manager()

    if mode:
        mode_manager.set_mode(ScanMode(mode))

    current_mode = mode_manager.current_mode
    min_confidence = mode_manager.min_confidence

    # =========================================================================
    # 2. Handle Framework Pack
    # =========================================================================
    active_pack = None
    active_pack_name = None

    if pack_name:
        active_pack = load_pack(pack_name)
        if active_pack:
            active_pack_name = active_pack.name
        else:
            console.print(f"[yellow]Warning: Pack '{pack_name}' not found[/yellow]")
    else:
        # Auto-detect pack
        suggested = detect_and_suggest_pack(scan_path)
        if suggested:
            active_pack = load_pack(suggested)
            if active_pack:
                active_pack_name = active_pack.name
                if not as_json:
                    console.print(f"[dim]Auto-detected framework pack: {active_pack_name}[/dim]")

    # =========================================================================
    # 3. Determine Output Path and Format
    # =========================================================================
    if output:
        output_path = Path(output)
    else:
        output_path = Path(".jnkn/jnkn.db")

    export_to_json = output_path.suffix.lower() == ".json"

    if export_to_json:
        db_path = output_path.with_suffix(".db")
    else:
        db_path = output_path

    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Capture context for JSON mode
    context_manager = renderer.capture() if as_json else _null_context()

    error_to_report = None
    response_data = None
    findings_summary = None

    with context_manager:
        try:
            if not as_json and not summary_only:
                console.print(f"🔍 Scanning [cyan]{scan_path}[/cyan]")
                console.print(
                    f"   Mode: [yellow]{current_mode.value}[/yellow] "
                    f"(min_confidence: {min_confidence})"
                )
                if db_path.exists() and not force:
                    console.print("   [dim]Using incremental cache[/dim]")

            # =================================================================
            # 4. Initialize Engine & Storage
            # =================================================================
            engine = create_default_engine()
            storage = SQLiteStorage(db_path)

            if force:
                storage.clear()

            # =================================================================
            # 5. Resolve Dependencies (Multi-Repo Support)
            # =================================================================
            scan_targets, manifest = _resolve_scan_targets(
                scan_path=scan_path,
                no_deps=no_deps,
                as_json=as_json,
                summary_only=summary_only,
            )

            # =================================================================
            # 6. Run Scan Loop
            # =================================================================
            total_stats_scanned = 0
            total_stats_failed = 0
            total_stats_skipped = 0
            total_stats_unchanged = 0
            total_stats_time = 0.0

            skip_dirs = SKIP_DIRS.copy()

            def progress(path: Path, current: int, total: int):
                if not as_json and verbose and not summary_only:
                    console.print(f"   [{current}/{total}] {path.name}")

            for target_path, repo_name in scan_targets:
                if not target_path.exists():
                    logger.warning(f"Scan target not found: {target_path}")
                    continue

                config = ScanConfig(
                    root_dir=target_path,
                    skip_dirs=skip_dirs,
                    incremental=not force,
                    source_repo_name=repo_name,
                )

                result = engine.scan_and_store(storage, config, progress_callback=progress)

                if result.is_err():
                    raise result.unwrap_err().cause or Exception(result.unwrap_err().message)

                stats = result.unwrap()

                # Accumulate stats
                total_stats_scanned += stats.files_scanned
                total_stats_failed += stats.files_failed
                total_stats_skipped += stats.files_skipped
                total_stats_unchanged += stats.files_unchanged
                total_stats_time += stats.scan_time_ms

                if not as_json and verbose and not summary_only:
                    if stats.files_scanned > 0:
                        console.print(f"   Parsed {stats.files_scanned} files in {repo_name}")

            # =================================================================
            # 7. Hydrate Graph for Stitching
            # =================================================================
            graph = storage.load_graph()

            # =================================================================
            # 8. Run Stitching (with Explicit Mapping Support)
            # =================================================================
            stitched_count, explicit_count, ignored_count, edges_to_save = _run_stitching(
                graph=graph,
                manifest=manifest,
                min_confidence=min_confidence,
                active_pack=active_pack,
                as_json=as_json,
                summary_only=summary_only,
            )

            # Save stitched edges
            if edges_to_save:
                storage.save_edges_batch(edges_to_save)

            # =================================================================
            # 9. Extract Top Findings
            # =================================================================
            graph = storage.load_graph()  # Reload with new edges

            if graph.node_count > 0:
                extractor = TopFindingsExtractor(graph)
                findings_summary = extractor.extract()

            # =================================================================
            # 10. Format Output
            # =================================================================
            if not as_json:
                formatter = ScanSummaryFormatter(console)
                formatter.format_summary(
                    nodes_found=graph.node_count,
                    edges_found=graph.edge_count,
                    stitched_count=stitched_count,
                    files_parsed=total_stats_scanned + total_stats_unchanged,
                    duration_sec=total_stats_time / 1000,
                    mode=current_mode,
                    findings_summary=findings_summary,
                    pack_name=active_pack_name,
                )

                # Show explicit mapping stats if any
                if explicit_count > 0 and not summary_only:
                    console.print(
                        f"   [dim]({explicit_count} from explicit mappings, "
                        f"{stitched_count - explicit_count} from fuzzy matching)[/dim]"
                    )

                if graph.node_count < 5:
                    echo_low_node_warning(graph.node_count)

            if export_to_json:
                with open(output_path, "w") as f:
                    json.dump(graph.to_dict(), f, indent=2)

            response_data = ScanSummaryResponse(
                total_files=total_stats_scanned + total_stats_unchanged,
                files_parsed=total_stats_scanned,
                files_skipped=total_stats_skipped,
                nodes_found=graph.node_count,
                edges_found=graph.edge_count,
                new_links_stitched=stitched_count,
                output_path=str(output_path),
                duration_sec=round(total_stats_time / 1000, 2),
                mode=current_mode.value,
                pack=active_pack_name,
                explicit_mappings_applied=explicit_count,
                repos_scanned=len(scan_targets),
            )

            storage.close()

        except Exception as e:
            error_to_report = e

    if as_json:
        if error_to_report:
            renderer.render_error(error_to_report)
            sys.exit(1)
        elif response_data:
            renderer.render_success(response_data)
    else:
        if error_to_report:
            raise error_to_report
