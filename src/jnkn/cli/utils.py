"""
CLI Utilities - Shared helper functions for command line operations.

This module provides common functionality used across various CLI commands,
including formatted printing, graph loading logic, and user guidance helpers.
"""

import json
from pathlib import Path
from typing import TYPE_CHECKING, Set, Union

import click

from jnkn.core.graph import DependencyGraph

from ..core.storage.sqlite import SQLiteStorage
from ..graph.lineage import LineageGraph

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


def load_graph(graph_file: str) -> Union[DependencyGraph, LineageGraph] | None:
    """
    Load a graph from file.
    
    Prioritizes SQLite (.db) for rustworkx backend.
    Falls back to JSON for legacy compatibility.
    """
    path = Path(graph_file)
    
    # 1. Resolve path
    target_file = None
    if path.is_dir():
        # Prefer DB over JSON
        if (path / ".jnkn/jnkn.db").exists():
            target_file = path / ".jnkn/jnkn.db"
        elif (path / "jnkn.db").exists():
            target_file = path / "jnkn.db"
        elif (path / ".jnkn/lineage.json").exists():
            target_file = path / ".jnkn/lineage.json"
        else:
            echo_error(f"No graph found in {path}")
            return None
    elif path.exists():
        target_file = path
    else:
        echo_error(f"File not found: {path}")
        return None

    # 2. Load based on extension
    if target_file.suffix == ".db":
        try:
            storage = SQLiteStorage(target_file)
            # Hydrate the rustworkx graph
            return storage.load_graph()
        except Exception as e:
            echo_error(f"Failed to load DB: {e}")
            return None
            
    elif target_file.suffix == ".json":
        try:
            data = json.loads(target_file.read_text())
            graph = LineageGraph()
            graph.load_from_dict(data)
            return graph
        except Exception as e:
            echo_error(f"Failed to load JSON: {e}")
            return None
            
    return None
