"""
Install Command - Fetch all dependencies.

Downloads and caches all git dependencies declared in jnkn.toml,
optionally using pinned versions from jnkn.lock for reproducibility.

Usage:
    jnkn install           # Fetch all dependencies
    jnkn install --frozen  # Use exact lockfile versions (CI mode)
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ...core.manifest import ProjectManifest
from ...core.resolver import DependencyError, DependencyResolver, DependencySource

console = Console()


@click.command()
@click.option(
    "--frozen",
    is_flag=True,
    help="Use exact versions from lockfile (fails if stale)",
)
@click.option(
    "--offline",
    is_flag=True,
    help="Only use cached dependencies (no network)",
)
@click.option(
    "--project-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Project directory containing jnkn.toml",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress output except errors",
)
def install(frozen: bool, offline: bool, project_dir: str, quiet: bool):
    """
    Fetch all dependencies.

    Downloads and caches all git dependencies declared in jnkn.toml.
    Use --frozen in CI to ensure reproducible builds from jnkn.lock.

    \b
    Examples:
        jnkn install             # Fetch all dependencies
        jnkn install --frozen    # Use lockfile versions (CI mode)
        jnkn install --offline   # Use cached only
    """
    project_root = Path(project_dir).resolve()
    manifest_path = project_root / "jnkn.toml"
    lockfile_path = project_root / "jnkn.lock"

    # Validate manifest exists
    if not manifest_path.exists():
        console.print("[red]Error:[/red] No jnkn.toml found")
        console.print("Run 'jnkn init' first to create one.")
        sys.exit(1)

    manifest = ProjectManifest.load(manifest_path)

    if not manifest.has_dependencies():
        if not quiet:
            console.print("[dim]No dependencies declared in jnkn.toml[/dim]")
        sys.exit(0)

    # Check lockfile exists for frozen mode
    if frozen and not lockfile_path.exists():
        console.print("[red]Error:[/red] --frozen requires jnkn.lock")
        console.print("Run 'jnkn lock' first to generate it.")
        sys.exit(1)

    if not quiet:
        mode_str = "[cyan]frozen[/cyan]" if frozen else "[cyan]latest[/cyan]"
        if offline:
            mode_str += " [yellow](offline)[/yellow]"
        console.print(f"[bold]📦 Installing dependencies ({mode_str})...[/bold]\n")

    # Resolve dependencies
    try:
        resolver = DependencyResolver(
            project_root=project_root,
            frozen=frozen,
            offline=offline,
        )
        result = resolver.resolve()
    except DependencyError as e:
        console.print(f"[red]Error:[/red] {e.message}")
        sys.exit(1)

    # Display results
    if not quiet:
        _print_results(result.dependencies, result.warnings)

    # Check for stale lockfile in frozen mode
    if frozen and result.lockfile_stale:
        console.print("\n[red]Error:[/red] Lockfile is stale")
        console.print("Run 'jnkn lock' to update jnkn.lock")
        sys.exit(1)

    # Print warnings
    for warning in result.warnings:
        console.print(f"[yellow]⚠️  {warning}[/yellow]")

    if not quiet:
        console.print(f"\n[green]✓ Installed {len(result.dependencies)} dependencies[/green]")


def _print_results(dependencies: list, warnings: list) -> None:
    """Print installation results as a table."""
    table = Table(show_header=True, header_style="bold")
    table.add_column("Dependency", style="cyan")
    table.add_column("Source", style="dim")
    table.add_column("Path/SHA")

    source_icons = {
        DependencySource.LOCAL: "📁",
        DependencySource.LOCAL_OVERRIDE: "📂",
        DependencySource.GIT: "🌐",
        DependencySource.GIT_LOCKED: "🔒",
    }

    for dep in dependencies:
        icon = source_icons.get(dep.source, "❓")
        source_label = f"{icon} {dep.source.value}"

        if dep.git_sha:
            path_or_sha = dep.git_sha[:8]
        else:
            # Shorten path for display
            try:
                path_or_sha = str(dep.path.relative_to(Path.cwd()))
            except ValueError:
                path_or_sha = str(dep.path)
            if len(path_or_sha) > 40:
                path_or_sha = "..." + path_or_sha[-37:]

        table.add_row(dep.name, source_label, path_or_sha)

    console.print(table)
