"""
Init Command - Onboarding Automation.

This command inspects the current directory to detect the technology stack
and generates a configuration file (.jnkn/config.yaml) tailored to the project.
It aims to get the user to their first successful scan in < 60 seconds.
"""

import os
import click
import yaml
from pathlib import Path
from typing import List, Set
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

console = Console()

# Default configuration template
DEFAULT_CONFIG = {
    "version": "1.0",
    "project_name": "my-project",
    "scan": {
        "include": [],  # Will be populated by detection
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
    "policy": {
        "critical_patterns": [
            ".*production.*",
            ".*billing.*",
            ".*security.*"
        ]
    }
}

def detect_stack(root_dir: Path) -> Set[str]:
    """
    Heuristically detect technologies used in the directory.
    """
    stack = set()
    
    # Python
    if list(root_dir.glob("**/*.py")) or (root_dir / "pyproject.toml").exists() or (root_dir / "requirements.txt").exists():
        stack.add("python")
        
    # Terraform
    if list(root_dir.glob("**/*.tf")):
        stack.add("terraform")
        
    # Kubernetes
    if list(root_dir.glob("**/*.yaml")) or list(root_dir.glob("**/*.yml")):
        # Naive check, but good enough for init suggestions
        stack.add("kubernetes")
        
    # dbt
    if (root_dir / "dbt_project.yml").exists():
        stack.add("dbt")
        
    # JavaScript/Node
    if (root_dir / "package.json").exists():
        stack.add("javascript")
        
    return stack

def create_gitignore(jnkn_dir: Path):
    """Ensure .jnkn/ directory is ignored by git."""
    gitignore = jnkn_dir.parent / ".gitignore"
    entry = "\n# jnkn\n.jnkn/\njnkn.db\n"
    
    if gitignore.exists():
        content = gitignore.read_text()
        if ".jnkn" not in content:
            with open(gitignore, "a") as f:
                f.write(entry)
    else:
        # Don't create .gitignore if it doesn't exist, user might not be using git
        pass

@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing configuration")
def init(force: bool):
    """
    Initialize Jnkan in the current directory.
    
    Detects your stack (Python, Terraform, dbt, etc.) and creates
    a .jnkn/config.yaml file with sensible defaults.
    """
    root_dir = Path.cwd()
    jnkn_dir = root_dir / ".jnkn"
    config_file = jnkn_dir / "config.yaml"

    console.print(Panel.fit("🚀 [bold blue]Jnkan Initialization[/bold blue]", border_style="blue"))

    # 1. Check existing
    if config_file.exists() and not force:
        console.print(f"[yellow]Configuration already exists at {config_file}[/yellow]")
        if not Confirm.ask("Do you want to overwrite it?"):
            console.print("Aborted.")
            return

    # 2. Detect Stack
    with console.status("[bold green]Detecting technology stack...[/bold green]"):
        stack = detect_stack(root_dir)
    
    if not stack:
        console.print("[yellow]No specific technologies detected. Using defaults.[/yellow]")
    else:
        console.print(f"✅ Detected: [cyan]{', '.join(stack)}[/cyan]")

    # 3. Build Config
    config = DEFAULT_CONFIG.copy()
    config["project_name"] = root_dir.name
    
    # Configure includes based on stack
    includes = []
    if "python" in stack:
        includes.append("**/*.py")
    if "terraform" in stack:
        includes.append("**/*.tf")
    if "javascript" in stack:
        includes.extend(["**/*.js", "**/*.ts", "**/*.tsx"])
    if "kubernetes" in stack:
        includes.extend(["**/*.yaml", "**/*.yml"])
    
    if not includes:
        includes = ["**/*"] # Default to everything if nothing specific found
        
    config["scan"]["include"] = includes

    # 4. Write Files
    jnkn_dir.mkdir(exist_ok=True)
    
    with open(config_file, "w") as f:
        yaml.dump(config, f, sort_keys=False, default_flow_style=False)
        
    create_gitignore(jnkn_dir)

    # 5. Success Message & Next Steps
    console.print(f"\n✨ [bold green]Initialized successfully![/bold green]")
    console.print(f"   Config created at: [dim]{config_file}[/dim]")
    
    console.print("\n[bold]Next Steps:[/bold]")
    console.print("1. Run a scan to build the dependency graph:")
    console.print("   [bold cyan]jnkn scan[/bold cyan]")
    console.print("\n2. Check the blast radius of a critical resource:")
    console.print("   [bold cyan]jnkn blast env:DATABASE_URL[/bold cyan]")