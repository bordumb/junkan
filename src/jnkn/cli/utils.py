"""
CLI Utilities - Shared helper functions for command line operations.

This module provides common functionality used across various CLI commands,
including formatted printing, graph loading logic, and user guidance helpers.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Optional, Set

import click

if TYPE_CHECKING:
    from ..graph.lineage import LineageGraph

# Directories to skip when scanning to improve performance and reduce noise
SKIP_DIRS: Set[str] = {
    ".git", ".jnkn", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", "eggs", "*.egg-info",
}


def echo_success(message: str) -> None:
    """
    Print a success message with a green checkmark.

    Args:
        message (str): The message to display.
    """
    click.echo(click.style(f"✅ {message}", fg="green"))


def echo_error(message: str) -> None:
    """
    Print an error message with a red cross.

    Args:
        message (str): The error message to display.
    """
    click.echo(click.style(f"❌ {message}", fg="red"), err=True)


def echo_warning(message: str) -> None:
    """
    Print a warning message with a yellow alert symbol.

    Args:
        message (str): The warning message to display.
    """
    click.echo(click.style(f"⚠️  {message}", fg="yellow"))


def echo_info(message: str) -> None:
    """
    Print an informational message, dimmed.

    Args:
        message (str): The info message to display.
    """
    click.echo(click.style(f"   {message}", dim=True))


def echo_low_node_warning(count: int) -> None:
    """
    Print a helpful warning when a scan finds very few nodes.

    This helps onboard users who may have misconfigured their scan or ignored
    important directories.

    Args:
        count (int): The number of nodes actually found.
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
    Load a LineageGraph from a file or directory path.

    Handles resolving directory paths to standard graph filenames (e.g., lineage.json).

    Args:
        graph_file (str): Path to a JSON file or a directory containing .jnkn/lineage.json.

    Returns:
        Optional[LineageGraph]: The loaded graph object, or None if loading failed.
    """
    from ..graph.lineage import LineageGraph

    graph_path = Path(graph_file)

    # Handle directory input by looking for default file locations
    if graph_path.is_dir():
        potential_files = [
            graph_path / ".jnkn/lineage.json",
            graph_path / "lineage.json",
            graph_path / ".jnkn/jnkn.db", # Though LineageGraph only reads JSON currently
        ]
        found = False
        for p in potential_files:
            if p.exists():
                graph_path = p
                found = True
                break
        
        if not found:
            echo_error(f"No lineage graph found in directory: {graph_file}")
            click.echo("Expected .jnkn/lineage.json. Run 'jnkn scan' first.")
            return None

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
