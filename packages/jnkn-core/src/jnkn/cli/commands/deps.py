"""
Deps Command - Dependency management and inspection.

Provides utilities for viewing and managing external dependencies,
including tree visualization and dependency tracing.

Usage:
    jnkn deps tree           # Show dependency tree
    jnkn deps why NODE_ID    # Explain why a node exists
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.tree import Tree

from ...core.manifest import ProjectManifest
from ...core.resolver import DependencyResolver, DependencySource

console = Console()


@click.group()
def deps():
    """
    Manage external dependencies.

    View and manage multi-repository dependencies declared in jnkn.toml.
    """
    pass


@deps.command("tree")
@click.option(
    "--project-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Project directory containing jnkn.toml",
)
@click.option(
    "--show-paths",
    is_flag=True,
    help="Show full resolved paths",
)
def deps_tree(project_dir: str, show_paths: bool):
    """
    Show dependency tree.

    Displays all declared dependencies and their resolution status.
    """
    project_root = Path(project_dir).resolve()
    manifest_path = project_root / "jnkn.toml"

    if not manifest_path.exists():
        console.print("[red]Error:[/red] No jnkn.toml found")
        console.print("Run 'jnkn init' first.")
        sys.exit(1)

    manifest = ProjectManifest.load(manifest_path)

    # Build tree
    tree = Tree(f"📦 [bold]{manifest.name}[/bold] ({manifest.version})")

    if not manifest.dependencies:
        tree.add("[dim]No dependencies declared[/dim]")
        console.print(tree)
        return

    # Try to resolve dependencies
    try:
        resolver = DependencyResolver(project_root, frozen=False, offline=True)
        result = resolver.resolve()
        resolved_map = {dep.name: dep for dep in result.dependencies}
    except Exception:
        resolved_map = {}

    # Add dependencies to tree
    deps_branch = tree.add("📚 Dependencies")

    for name, spec in manifest.dependencies.items():
        resolved = resolved_map.get(name)

        # Build label
        if spec.git:
            source_info = f"git: {spec.git}"
            if spec.branch:
                source_info += f" @ {spec.branch}"
            elif spec.tag:
                source_info += f" @ {spec.tag}"
        elif spec.path:
            source_info = f"path: {spec.path}"
        else:
            source_info = "unknown"

        if resolved:
            icon = _get_source_icon(resolved.source)
            status = f"[green]✓[/green] {icon}"
            if resolved.git_sha:
                status += f" ({resolved.git_sha[:8]})"
        else:
            status = "[yellow]⚠ not resolved[/yellow]"

        branch = deps_branch.add(f"{status} [cyan]{name}[/cyan]")
        branch.add(f"[dim]{source_info}[/dim]")

        if show_paths and resolved:
            try:
                rel_path = resolved.path.relative_to(project_root.parent)
            except ValueError:
                rel_path = resolved.path
            branch.add(f"[dim]→ {rel_path}[/dim]")

    # Add overrides section if present
    if manifest.source_overrides:
        overrides_branch = tree.add("🔄 Local Overrides")
        for name, spec in manifest.source_overrides.items():
            if spec.path:
                override_path = (project_root / spec.path).resolve()
                exists = override_path.exists()
                icon = "[green]✓[/green]" if exists else "[red]✗[/red]"
                overrides_branch.add(f"{icon} {name}: {spec.path}")

    console.print(tree)


@deps.command("why")
@click.argument("node_id")
@click.option(
    "--project-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Project directory containing jnkn.toml",
)
def deps_why(node_id: str, project_dir: str):
    """
    Explain why a node exists in the graph.

    Shows which dependency or local file contributed the node.

    \b
    Examples:
        jnkn deps why "infra:output:database_url"
        jnkn deps why "env:API_KEY"
    """
    project_root = Path(project_dir).resolve()
    db_path = project_root / ".jnkn" / "jnkn.db"

    if not db_path.exists():
        console.print("[red]Error:[/red] No graph database found")
        console.print("Run 'jnkn scan' first.")
        sys.exit(1)

    # Load graph
    from ...core.storage.sqlite import SQLiteStorage

    try:
        storage = SQLiteStorage(db_path)
        graph = storage.load_graph()
        storage.close()
    except Exception as e:
        console.print(f"[red]Error loading graph:[/red] {e}")
        sys.exit(1)

    # Find node
    node = graph.get_node(node_id)
    if not node:
        # Try fuzzy search
        matches = graph.find_nodes(node_id)
        if matches:
            console.print(f"[yellow]Node '{node_id}' not found. Did you mean:[/yellow]")
            for match in matches[:5]:
                console.print(f"  • {match}")
            sys.exit(1)
        else:
            console.print(f"[red]Node not found:[/red] {node_id}")
            sys.exit(1)

    # Display node info
    console.print(f"\n[bold]Node: {node_id}[/bold]\n")

    # Basic info
    console.print(f"  Type: [cyan]{node.type.value}[/cyan]")
    console.print(f"  Name: {node.name}")

    if node.path:
        console.print(f"  File: {node.path}")

    # Source repo (from metadata)
    source_repo = node.metadata.get("source_repo") if node.metadata else None
    if source_repo:
        console.print(f"  Source: [green]{source_repo}[/green]")

    # Tokens
    if node.tokens:
        console.print(f"  Tokens: {', '.join(node.tokens)}")

    # Incoming edges (providers)
    in_edges = graph.get_in_edges(node_id)
    if in_edges:
        console.print(f"\n[bold]Provided by ({len(in_edges)}):[/bold]")
        for edge in in_edges:
            source = graph.get_node(edge.source_id)
            source_name = source.name if source else edge.source_id
            conf = f" ({edge.confidence:.0%})" if edge.confidence else ""
            console.print(f"  ← {edge.source_id} [dim]{conf}[/dim]")

    # Outgoing edges (consumers)
    out_edges = graph.get_out_edges(node_id)
    if out_edges:
        console.print(f"\n[bold]Provides to ({len(out_edges)}):[/bold]")
        for edge in out_edges:
            target = graph.get_node(edge.target_id)
            target_name = target.name if target else edge.target_id
            conf = f" ({edge.confidence:.0%})" if edge.confidence else ""
            console.print(f"  → {edge.target_id} [dim]{conf}[/dim]")


@deps.command("status")
@click.option(
    "--project-dir",
    "-p",
    type=click.Path(exists=True, file_okay=False),
    default=".",
    help="Project directory containing jnkn.toml",
)
def deps_status(project_dir: str):
    """
    Show dependency resolution status.

    Quick overview of which dependencies are resolved and how.
    """
    project_root = Path(project_dir).resolve()
    manifest_path = project_root / "jnkn.toml"

    if not manifest_path.exists():
        console.print("[dim]No jnkn.toml found - no dependencies[/dim]")
        return

    manifest = ProjectManifest.load(manifest_path)

    if not manifest.dependencies:
        console.print("[dim]No dependencies declared[/dim]")
        return

    # Try to resolve
    try:
        resolver = DependencyResolver(project_root, frozen=False, offline=True)
        result = resolver.resolve()
    except Exception as e:
        console.print(f"[red]Resolution failed:[/red] {e}")
        return

    # Summary
    total = len(manifest.dependencies)
    resolved = len(result.dependencies)
    local = sum(
        1
        for d in result.dependencies
        if d.source in (DependencySource.LOCAL, DependencySource.LOCAL_OVERRIDE)
    )
    git = sum(
        1
        for d in result.dependencies
        if d.source in (DependencySource.GIT, DependencySource.GIT_LOCKED)
    )

    console.print(f"[bold]Dependencies: {resolved}/{total} resolved[/bold]")
    console.print(f"  📁 Local: {local}")
    console.print(f"  🌐 Git: {git}")

    if result.warnings:
        console.print(f"\n[yellow]Warnings ({len(result.warnings)}):[/yellow]")
        for warning in result.warnings:
            console.print(f"  ⚠️  {warning}")


def _get_source_icon(source: DependencySource) -> str:
    """Get icon for dependency source type."""
    icons = {
        DependencySource.LOCAL: "📁",
        DependencySource.LOCAL_OVERRIDE: "📂",
        DependencySource.GIT: "🌐",
        DependencySource.GIT_LOCKED: "🔒",
    }
    return icons.get(source, "❓")
