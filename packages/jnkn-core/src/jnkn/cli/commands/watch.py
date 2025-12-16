"""
Watch Command.

Starts the file system watcher daemon for real-time graph updates.
"""

import logging
from pathlib import Path

import click
from rich.console import Console


console = Console()


@click.command()
@click.argument("directory", default=".", type=click.Path(exists=True))
@click.option("-d", "--db-path", default=".jnkn/jnkn.db", help="Path to SQLite database")
def watch(directory: str, db_path: str):
    """
    Start the Auto-Watch Daemon.

    Monitors the project directory for file changes and updates the
    dependency graph in real-time. This eliminates the need to run
    'jnkn scan' manually.

    The daemon updates the SQLite database immediately, so other tools
    like the LSP server or 'jnkn check' always see fresh data.
    """
    # Configure logging to ensure we see the watcher events
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(message)s",
        datefmt="[%X]"
    )

    # Lazy import: Only import the watcher (and watchdog) when this command actually RUNS.
    from ..watcher import FileSystemWatcher

    root_dir = Path(directory).resolve()
    database_file = Path(db_path).resolve()

    # Ensure DB directory exists
    database_file.parent.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold green]Jnkn Auto-Watch[/bold green]")
    console.print(f"Watching: [cyan]{root_dir}[/cyan]")
    
    watcher = FileSystemWatcher(root_dir, database_file)
    watcher.start()