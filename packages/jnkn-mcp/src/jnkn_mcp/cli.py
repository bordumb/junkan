"""
Jnkn AI CLI.

Provides command-line utilities for managing the Jnkn AI server and
integrating it with IDEs like Cursor and Windsurf.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Literal

import click
import yaml
from rich.console import Console

# --- Configuration & Constants ---

console = Console()

CURSOR_CONFIG_PATH = (
    Path.home()
    / "Library"
    / "Application Support"
    / "Cursor"
    / "User"
    / "globalStorage"
    / "cursor.mcp"
    / "mcp.json"
)
WINDSURF_CONFIG_PATH = Path.home() / ".codeium" / "windsurf" / "mcp_config.json"
CONTINUE_CONFIG_PATH = Path.home() / ".continue" / "config.yaml"


# --- Helpers ---


def _generate_server_config(
    mode: Literal["dev", "prod"], repo_root: Path, uv_path: str = "uv"
) -> Dict[str, Any]:
    """
    Generates the MCP server configuration dictionary based on the installation mode.

    Args:
        mode: 'dev' runs from source using uv; 'prod' runs the installed binary.
        repo_root: The absolute path to the source code (used in dev mode).
        uv_path: Path to the uv executable.

    Returns:
        A dictionary containing the 'command' and 'args' for the MCP server.
    """
    # The database path is always relative to the active IDE workspace
    db_arg = "${workspaceFolder}/.jnkn/jnkn.db"

    if mode == "dev":
        return {
            "command": uv_path,
            "args": [
                "run",
                "--directory",
                str(repo_root),
                "jnkn-mcp",
                "start",
                "--stdio",
                "--db-path",
                db_arg,
            ],
            "env": {},
            "disabled": False,
            "autoRestart": True,
        }

    # Prod mode assumes 'jnkn-mcp' is in the system PATH
    return {
        "command": "jnkn-mcp",
        "args": ["start", "--stdio", "--db-path", db_arg],
        "env": {},
        "disabled": False,
        "autoRestart": True,
    }


def _update_json_config(
    config_path: Path,
    server_name: str,
    server_config: dict,
    wrapper_key: str = "mcpServers",
) -> None:
    """
    Updates a JSON configuration file with the new server config.

    Args:
        config_path: Path to the JSON file.
        server_name: Key to use for this server in the config.
        server_config: The configuration dictionary to insert.
        wrapper_key: The parent key containing the server list (e.g., 'mcpServers').
    """
    if not config_path.parent.exists():
        console.print(f"[yellow]Directory not found:[/yellow] {config_path.parent}")
        return

    data = {}
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError:
            console.print(
                f"[red]Corrupt config found. Backing up to {config_path}.bak[/red]"
            )
            shutil.copy(config_path, str(config_path) + ".bak")

    if wrapper_key not in data:
        data[wrapper_key] = {}

    data[wrapper_key][server_name] = server_config

    try:
        with open(config_path, "w") as f:
            json.dump(data, f, indent=2)
        console.print(f"[green]Registered {server_name} in {config_path}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to write JSON:[/red] {e}")


def _update_yaml_config(
    config_path: Path, server_name: str, server_config: dict
) -> None:
    """
    Updates a YAML configuration file (specifically for Continue/VSCode).

    Args:
        config_path: Path to the YAML file.
        server_name: The name of the server to add/update.
        server_config: The configuration dictionary.
    """
    if not config_path.exists():
        console.print(f"[yellow]Config not found:[/yellow] {config_path}")
        return

    try:
        with open(config_path, "r") as f:
            data = yaml.safe_load(f) or {}

        data.setdefault("mcpServers", [])

        # Remove existing entry with same name to allow update
        data["mcpServers"] = [
            s for s in data["mcpServers"] if s.get("name") != server_name
        ]

        # Continue expects 'name' inside the config object
        full_config = {"name": server_name, "type": "stdio", **server_config}
        data["mcpServers"].append(full_config)

        with open(config_path, "w") as f:
            yaml.dump(data, f, sort_keys=False, indent=2)

        console.print(f"[green]Registered {server_name} in {config_path}[/green]")
    except Exception as e:
        console.print(f"[red]Failed to write YAML:[/red] {e}")


# --- CLI Commands ---


@click.group()
def cli():
    """Jnkn AI: The Architectural Context Bridge for LLMs."""
    pass


@cli.command()
@click.option("--port", default=8000, help="Port to run the MCP server on (SSE mode).")
@click.option(
    "--stdio", is_flag=True, default=True, help="Run in stdio mode (default)."
)
@click.option("--db-path", default=".jnkn/jnkn.db", help="Path to the dependency graph")
def start(port: int, stdio: bool, db_path: str):
    """
    Start the Jnkn AI MCP Server.
    """
    from .server import mcp, _graph_manager

    _graph_manager.db_path = Path(db_path)

    if stdio:
        mcp.run(transport="stdio")
    else:
        mcp.run(transport="sse", port=port)


@cli.command("install-cursor")
@click.option("--name", default="jnkn", help="Name for the MCP server in Cursor.")
@click.option(
    "--mode",
    type=click.Choice(["dev", "prod"]),
    default="dev",
    help="Link to source (dev) or global install (prod).",
)
def install_cursor(name: str, mode: str):
    """Configure Cursor to use Jnkn AI."""
    uv_path = shutil.which("uv") or "uv"
    repo_root = Path.cwd().absolute()

    config = _generate_server_config(mode, repo_root, uv_path)
    _update_json_config(CURSOR_CONFIG_PATH, name, config)


@cli.command("install-windsurf")
@click.option("--name", default="jnkn", help="Name for the MCP server in Windsurf.")
@click.option(
    "--mode",
    type=click.Choice(["dev", "prod"]),
    default="dev",
    help="Link to source (dev) or global install (prod).",
)
def install_windsurf(name: str, mode: str):
    """Configure Windsurf to use Jnkn AI."""
    uv_path = shutil.which("uv") or "uv"
    repo_root = Path.cwd().absolute()

    config = _generate_server_config(mode, repo_root, uv_path)
    # Windsurf wraps configs in "mcpServers"
    _update_json_config(WINDSURF_CONFIG_PATH, name, config, wrapper_key="mcpServers")


@cli.command("install-vscode")
@click.option("--name", default="jnkn", help="Name for the MCP server in Continue.")
@click.option(
    "--mode",
    type=click.Choice(["dev", "prod"]),
    default="dev",
    help="Link to source (dev) or global install (prod).",
)
def install_vscode(name: str, mode: str):
    """Configure VS Code (via Continue) to use Jnkn AI."""
    uv_path = shutil.which("uv") or "uv"
    repo_root = Path.cwd().absolute()

    config = _generate_server_config(mode, repo_root, uv_path)
    _update_yaml_config(CONTINUE_CONFIG_PATH, name, config)

    console.print(
        "Please [bold]Reload Window[/bold] in VS Code for changes to take effect."
    )


if __name__ == "__main__":
    cli()
