"""
CLI Utilities - Shared helpers for CLI commands.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

import click

if TYPE_CHECKING:
    from ..graph.lineage import LineageGraph

# Directories to skip when scanning
SKIP_DIRS: Set[str] = {
    ".git", ".jnkn", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", "eggs", "*.egg-info",
}


def echo_success(message: str) -> None:
    """Print a success message."""
    click.echo(click.style(f"✅ {message}", fg="green"))


def echo_error(message: str) -> None:
    """Print an error message."""
    click.echo(click.style(f"❌ {message}", fg="red"), err=True)


def echo_warning(message: str) -> None:
    """Print a warning message."""
    click.echo(click.style(f"⚠️  {message}", fg="yellow"))


def echo_info(message: str) -> None:
    """Print an info message."""
    click.echo(click.style(f"   {message}", dim=True))


def echo_low_node_warning(count: int) -> None:
    """
    Print a helpful warning when a scan finds very few nodes.
    
    This is critical for onboarding: if a user sees 0-5 nodes, they often assume
    the tool is broken rather than misconfigured.
    """
    click.echo()
    click.echo(click.style(f"⚠️  Low node count detected! ({count} nodes found)", fg="yellow", bold=True))
    click.echo(click.style("   This usually means the parser missed your files.", fg="yellow"))
    click.echo()
    click.echo("   Troubleshooting:")
    click.echo("   1. Are you running this from the project root?")
    click.echo("   2. Check .jnknignore (we skip .git, venv, node_modules by default)")
    click.echo("   3. Run with --verbose to see exactly what is being skipped:")
    click.echo(click.style("      jnkn scan --verbose", fg="cyan"))
    click.echo()


def load_graph(graph_file: str) -> Optional["LineageGraph"]:
    """
    Load a LineageGraph from a JSON file.
    
    Returns None if file doesn't exist or can't be loaded.
    """
    from ..graph.lineage import LineageGraph

    graph_path = Path(graph_file)

    if not graph_path.exists():
        echo_error(f"Graph file not found: {graph_file}")
        click.echo("Run 'jnkn scan <directory>' first to create it.")
        return None

    try:
        data = json.loads(graph_path.read_text())
        graph = LineageGraph()
        graph.load_from_dict(data)
        return graph
    except Exception as e:
        echo_error(f"Failed to load graph: {e}")
        return None
