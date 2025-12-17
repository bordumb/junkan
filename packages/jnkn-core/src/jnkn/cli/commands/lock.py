"""
Lock Command - Generate or update the lockfile.

Resolves all git dependencies and pins them to specific commit SHAs
in jnkn.lock for reproducible builds across machines and CI.

Usage:
    jnkn lock              # Generate/update lockfile
    jnkn lock --update X   # Update specific dependency
    jnkn lock --dry-run    # Show what would change
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from ...core.git_fetcher import GitFetcher
from ...core.lockfile import Lockfile, create_locked_package
from ...core.manifest import ProjectManifest

console = Console()


@click.command()
@click.option(
    "--update",
    "update_name",
    help="Update only a specific dependency",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would change without writing",
)
@click.option(
    "--project-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Project directory containing jnkn.toml",
)
def lock(update_name: str | None, dry_run: bool, project_dir: str):
    """
    Generate or update the dependency lockfile.

    Resolves all git dependencies and pins them to specific commit SHAs
    in jnkn.lock. This ensures reproducible builds across machines and CI.

    \b
    Examples:
        jnkn lock                    # Lock all dependencies
        jnkn lock --update infra     # Update just 'infra'
        jnkn lock --dry-run          # Preview changes
    """
    project_root = Path(project_dir).resolve()
    manifest_path = project_root / "jnkn.toml"
    lockfile_path = project_root / "jnkn.lock"

    # Load manifest
    if not manifest_path.exists():
        console.print("[red]Error:[/red] No jnkn.toml found in current directory")
        console.print("Run 'jnkn init' first to create one.")
        sys.exit(1)

    manifest = ProjectManifest.load(manifest_path)

    if not manifest.has_dependencies():
        console.print("[yellow]No dependencies declared in jnkn.toml[/yellow]")
        sys.exit(0)

    # Load existing lockfile
    lockfile = Lockfile.load(lockfile_path)

    # Filter dependencies to process
    deps_to_process = dict(manifest.dependencies)
    if update_name:
        if update_name not in deps_to_process:
            console.print(f"[red]Error:[/red] Dependency '{update_name}' not found")
            sys.exit(1)
        deps_to_process = {update_name: deps_to_process[update_name]}

    # Track changes
    changes = []
    git_fetcher = GitFetcher()

    console.print("[bold]📦 Locking dependencies...[/bold]\n")

    for name, spec in deps_to_process.items():
        # Skip local-only dependencies
        if not spec.git:
            console.print(f"  [dim]⏭️  {name}: Local path (skipped)[/dim]")
            continue

        # Check for local override
        if name in manifest.source_overrides:
            override = manifest.source_overrides[name]
            override_path = (project_root / override.path).resolve() if override.path else None
            if override_path and override_path.exists():
                console.print(f"  [dim]⏭️  {name}: Local override active (skipped)[/dim]")
                continue

        # Resolve current SHA
        with console.status(f"[bold]Resolving {name}...[/bold]"):
            try:
                cache_path = git_fetcher.fetch(name, spec)
                current_sha = git_fetcher.get_current_sha(cache_path)
            except Exception as e:
                console.print(f"  [red]❌ {name}: Failed to fetch ({e})[/red]")
                continue

        # Check if changed
        existing = lockfile.get_package(name)
        if existing and existing.rev == current_sha:
            console.print(f"  [green]✓[/green] {name}: {current_sha[:8]} (unchanged)")
        else:
            old_sha = existing.rev[:8] if existing and existing.rev else "new"
            console.print(f"  [yellow]↑[/yellow] {name}: {old_sha} → {current_sha[:8]}")

            changes.append(
                create_locked_package(
                    name=name,
                    git_url=spec.git,
                    rev=current_sha,
                    branch=spec.branch,
                    tag=spec.tag,
                )
            )

    # Summary
    console.print()
    if not changes:
        console.print("[green]✓ Lockfile is up to date[/green]")
        sys.exit(0)

    if dry_run:
        console.print(f"[yellow]Would update {len(changes)} package(s)[/yellow]")
        _print_changes_table(changes, lockfile)
        sys.exit(0)

    # Apply changes
    for pkg in changes:
        lockfile.update_package(pkg)

    lockfile.save(lockfile_path)
    console.print(f"[green]✓ Updated {len(changes)} package(s) in jnkn.lock[/green]")


def _print_changes_table(changes: list, lockfile: Lockfile) -> None:
    """Print a table of pending changes."""
    table = Table(title="Pending Changes")
    table.add_column("Package", style="cyan")
    table.add_column("Old SHA", style="dim")
    table.add_column("New SHA", style="green")
    table.add_column("Branch/Tag")

    for pkg in changes:
        old = lockfile.get_package(pkg.name)
        old_sha = old.rev[:8] if old and old.rev else "-"
        ref = pkg.tag or pkg.branch or "-"

        table.add_row(
            pkg.name,
            old_sha,
            pkg.rev[:8] if pkg.rev else "-",
            ref,
        )

    console.print(table)
