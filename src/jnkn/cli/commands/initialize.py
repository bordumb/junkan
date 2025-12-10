"""
Init Command - Onboarding Automation.

This module handles the `jnkn init` command, which bootstraps a project
with a configuration file tailored to the detected technology stack.
"""

import uuid
from pathlib import Path
from typing import Set

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

# Default configuration template
DEFAULT_CONFIG = {
    "version": "1.0",
    "project_name": "my-project",
    "scan": {
        "include": [],
        "exclude": [
            "**/node_modules/**",
            "**/venv/**",
            "**/.terraform/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/build/**"
        ],
        "min_confidence": 0.5
    },
    "telemetry": {
        "enabled": False,
        "distinct_id": ""
    }
}

def detect_stack(root_dir: Path) -> Set[str]:
    """
    Heuristically detect technologies used in the directory.

    Scans the given directory for specific file extensions or indicators
    (e.g., `dbt_project.yml` for dbt, `*.tf` for Terraform) to determine
    which technologies are present.

    Args:
        root_dir: The directory to inspect.

    Returns:
        Set[str]: A set of detected technology names (e.g., {'python', 'terraform'}).
    """
    stack = set()
    
    # Python detection: .py files or standard config files
    if list(root_dir.glob("**/*.py")) or (root_dir / "pyproject.toml").exists():
        stack.add("python")
        
    # Terraform detection: .tf files
    if list(root_dir.glob("**/*.tf")):
        stack.add("terraform")
        
    # Kubernetes detection: YAML files (naive check)
    if list(root_dir.glob("**/*.yaml")) or list(root_dir.glob("**/*.yml")):
        stack.add("kubernetes")
        
    # dbt detection: project config file
    if (root_dir / "dbt_project.yml").exists():
        stack.add("dbt")
        
    # JS/TS detection: package.json
    if (root_dir / "package.json").exists():
        stack.add("javascript")
        
    return stack

def create_gitignore(jnkn_dir: Path):
    """
    Ensure the .jnkn/ directory is ignored by git.

    Checks the parent directory's `.gitignore` file. If `.jnkn` is not
    already present, it appends an entry to prevent the local database
    and config from being committed accidentally.

    Args:
        jnkn_dir: The path to the .jnkn directory being created.
    """
    gitignore = jnkn_dir.parent / ".gitignore"
    entry = "\n# jnkn\n.jnkn/\njnkn.db\n"
    
    if gitignore.exists():
        content = gitignore.read_text()
        if ".jnkn" not in content:
            with open(gitignore, "a") as f:
                f.write(entry)

@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing configuration")
def init(force: bool):
    """
    Initialize Jnkan in the current directory.

    This command performs the following actions:
    1. Detects the technology stack in the current directory.
    2. Generates a tailored `.jnkn/config.yaml` file.
    3. Asks the user for telemetry consent.
    4. Updates `.gitignore` to exclude build artifacts.
    """
    root_dir = Path.cwd()
    jnkn_dir = root_dir / ".jnkn"
    config_file = jnkn_dir / "config.yaml"

    console.print(Panel.fit("🚀 [bold blue]Jnkn Initialization[/bold blue]", border_style="blue"))

    if config_file.exists() and not force:
        console.print(f"[yellow]Configuration already exists at {config_file}[/yellow]")
        if not Confirm.ask("Do you want to overwrite it?"):
            console.print("Aborted.")
            return

    # Stack Detection
    with console.status("[bold green]Detecting technology stack...[/bold green]"):
        stack = detect_stack(root_dir)

    if not stack:
        console.print("[yellow]No specific technologies detected. Using defaults.[/yellow]")
    else:
        console.print(f"✅ Detected: [cyan]{', '.join(stack)}[/cyan]")

    # Config Builder
    config = DEFAULT_CONFIG.copy()
    config["project_name"] = root_dir.name

    includes = []
    if "python" in stack: includes.append("**/*.py")
    if "terraform" in stack: includes.append("**/*.tf")
    if "javascript" in stack: includes.extend(["**/*.js", "**/*.ts", "**/*.tsx"])
    if "kubernetes" in stack: includes.extend(["**/*.yaml", "**/*.yml"])
    
    # Fallback if nothing specific was found
    if not includes: includes = ["**/*"]
    config["scan"]["include"] = includes

    # Telemetry Opt-in
    console.print("\n[bold]Telemetry[/bold]")
    allow_telemetry = Confirm.ask(
        "Allow anonymous usage statistics to help us improve Jnkan?", 
        default=True
    )
    
    config["telemetry"]["enabled"] = allow_telemetry
    config["telemetry"]["distinct_id"] = str(uuid.uuid4())

    # Write Files
    jnkn_dir.mkdir(exist_ok=True)
    with open(config_file, "w") as f:
        yaml.dump(config, f, sort_keys=False, default_flow_style=False)

    create_gitignore(jnkn_dir)

    console.print("\n✨ [bold green]Initialized successfully![/bold green]")
    console.print(f"   Config created at: [dim]{config_file}[/dim]")
