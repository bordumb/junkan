"""
Init Command - Onboarding Automation.

This module handles the `jnkn init` command, which bootstraps a project
with a configuration file tailored to the detected technology stack.

Security Note:
    This command includes a specific "Privacy Manifesto" display to ensure
    users understand exactly what data remains local vs what is sent.
"""

import uuid
from pathlib import Path
from typing import Set

import click
import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm

from ...core.demo import DemoManager
from ...core.mode import ModeManager
from ...core.packs import detect_and_suggest_pack, get_available_packs, load_pack

console = Console()

# Default configuration template
# Configured for "Discovery Mode" by default to show immediate value
DEFAULT_CONFIG = {
    "version": "1.0",
    "project_name": "my-project",
    "mode": "discovery",  # Start in discovery mode
    "pack": None,  # Framework pack name
    "scan": {
        "include": [],
        "exclude": [
            "**/node_modules/**",
            "**/venv/**",
            "**/.terraform/**",
            "**/__pycache__/**",
            "**/dist/**",
            "**/build/**",
        ],
        "min_confidence": 0.3,  # Lower default for discovery mode
    },
    "telemetry": {"enabled": False, "distinct_id": ""},
}


def detect_stack(root_dir: Path) -> Set[str]:
    """
    Heuristically detect technologies used in the directory.
    """
    stack = set()
    if list(root_dir.glob("**/*.py")) or (root_dir / "pyproject.toml").exists():
        stack.add("python")
    if list(root_dir.glob("**/*.tf")):
        stack.add("terraform")
    if list(root_dir.glob("**/*.yaml")) or list(root_dir.glob("**/*.yml")):
        stack.add("kubernetes")
    if (root_dir / "dbt_project.yml").exists():
        stack.add("dbt")
    if (root_dir / "package.json").exists():
        stack.add("javascript")
    return stack


def create_gitignore(jnkn_dir: Path):
    """Ensure the .jnkn/ directory is ignored by git."""
    gitignore = jnkn_dir.parent / ".gitignore"
    entry = "\n# jnkn\n.jnkn/\njnkn.db\n"

    if not gitignore.exists():
        with open(gitignore, "w") as f:
            f.write(entry)
    else:
        content = gitignore.read_text()
        if ".jnkn" not in content:
            with open(gitignore, "a") as f:
                f.write(entry)


def _display_privacy_manifesto():
    """Display the privacy and telemetry transparency panel."""
    manifesto = """
**Your Code Stays Here.**

Jnkan is built for security-conscious environments. We want to be hyper-transparent about how we handle your data:

* ❌ **WE DO NOT** collect source code, file names, or secrets.
* ❌ **WE DO NOT** collect environment variable values.
* ❌ **WE DO NOT** upload your dependency graph.

**What We Do Collect (Telemetry):**
* ✅ **Anonymous Metrics:** Command run counts (e.g., `scan`, `check`), execution duration, and success/failure status.
* ✅ **System Info:** Python version, OS platform, and CLI version.

*This helps us improve performance and prioritize feature development.*
    """
    console.print(
        Panel(
            Markdown(manifesto.strip()),
            title="🔒 [bold]Security & Privacy[/bold]",
            border_style="green",
            expand=False,
        )
    )


def _init_project(
    root_dir: Path,
    force: bool,
    is_demo: bool = False,
    telemetry_opt_in: bool | None = None,
    pack_name: str | None = None,
):
    """Internal helper to initialize a project."""
    jnkn_dir = root_dir / ".jnkn"
    config_file = jnkn_dir / "config.yaml"

    # Stack Detection
    # If demo mode, we force the known stack
    if is_demo:
        stack = {"python", "terraform", "kubernetes"}
    else:
        with console.status("[bold green]Detecting technology stack...[/bold green]"):
            stack = detect_stack(root_dir)

    if not is_demo:
        if not stack:
            console.print("[yellow]No specific technologies detected. Using defaults.[/yellow]")
        else:
            console.print(f"✅ Detected: [cyan]{', '.join(stack)}[/cyan]")

    # Config Builder
    config = DEFAULT_CONFIG.copy()
    config["project_name"] = root_dir.name

    # === Pack Detection/Selection (add after stack detection) ===
    if pack_name:
        pack = load_pack(pack_name)
        if pack:
            config["pack"] = pack_name
            console.print(f"✅ Using pack: [cyan]{pack_name}[/cyan]")
        else:
            available = get_available_packs()
            console.print(f"[yellow]Pack '{pack_name}' not found.[/yellow]")
            console.print(f"Available packs: {', '.join(available)}")
    elif not is_demo:
        # Auto-detect
        suggested = detect_and_suggest_pack(root_dir)
        if suggested:
            console.print(f"\n💡 Detected project type: [cyan]{suggested}[/cyan]")
            pack = load_pack(suggested)
            if pack:
                console.print(f"   {pack.description.split(chr(10))[0]}")
            if Confirm.ask(f"Use the {suggested} framework pack?", default=True):
                config["pack"] = suggested
                console.print(f"✅ Pack enabled: [cyan]{suggested}[/cyan]")

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
        includes = ["**/*"]

    config["scan"]["include"] = includes

    # Telemetry Configuration
    # Logic:
    # 1. If --telemetry or --no-telemetry passed explicitly, honor it.
    # 2. If --demo mode, enable by default (it's a sandbox).
    # 3. Otherwise, show the manifesto and ask.

    if telemetry_opt_in is not None:
        allow_telemetry = telemetry_opt_in
        status = "ENABLED" if allow_telemetry else "DISABLED"
        console.print(f"\n[bold]Telemetry:[/bold] {status} (via flag)")
    elif is_demo:
        allow_telemetry = True
    else:
        _display_privacy_manifesto()
        allow_telemetry = Confirm.ask("\nAllow anonymous usage statistics?", default=True)

    config["telemetry"]["enabled"] = allow_telemetry
    # Only generate a distinct ID if telemetry is enabled or might be enabled later
    # This ID is random UUID v4 and contains no PII
    config["telemetry"]["distinct_id"] = str(uuid.uuid4())

    # Write Files
    jnkn_dir.mkdir(exist_ok=True)
    with open(config_file, "w") as f:
        yaml.dump(config, f, sort_keys=False, default_flow_style=False)

    create_gitignore(jnkn_dir)

    # Initialize mode manager with discovery mode
    mode_manager = ModeManager()
    mode_manager.reset_to_discovery()

    console.print("\n✨ [bold green]Initialized successfully![/bold green]")
    console.print(f"   Config created at: [dim]{config_file}[/dim]")


@click.command()
@click.option("--force", is_flag=True, help="Overwrite existing configuration")
@click.option("--demo", is_flag=True, help="Download example repo to try Jnkan instantly")
@click.option("--multirepo", is_flag=True, help="Use multi-repo structure for demo")
@click.option(
    "--telemetry/--no-telemetry",
    default=None,
    help="Explicitly enable or disable telemetry (skips prompt)",
)
@click.option(
    "--pack",
    "pack_name",
    help="Use a specific framework pack (e.g., django-aws, fastapi-aws)",
)
@click.option(
    "--list-packs",
    is_flag=True,
    help="List available framework packs and exit",
)
def init(
    force: bool,
    demo: bool,
    multirepo: bool,
    telemetry: bool | None,
    pack_name: str | None,
    list_packs: bool,
):
    """
    Initialize Jnkan in the current directory.

    \b
    Framework Packs:
      Packs are pre-tuned configurations for specific technology stacks.
      They reduce false positives and improve accuracy out-of-the-box.

    \b
    Examples:
        jnkn init                      # Auto-detect and configure
        jnkn init --pack django-aws    # Use Django+AWS pack
        jnkn init --demo               # Try with sample project
        jnkn init --list-packs         # See available packs
    """
    console.print(Panel.fit("🚀 [bold blue]Jnkan Initialization[/bold blue]", border_style="blue"))

    # Handle --list-packs
    if list_packs:
        console.print("\n[bold]Available Framework Packs:[/bold]\n")
        for name in get_available_packs():
            pack = load_pack(name)
            if pack:
                console.print(f"  [cyan]{name}[/cyan]")
                console.print(f"    {pack.description.split(chr(10))[0]}")
                console.print()
        return

    if demo:
        console.print("[cyan]Provisioning demo environment...[/cyan]")

        # Instantiate DemoManager with CWD to fix TypeError
        manager = DemoManager(Path.cwd())

        # Pass multirepo flag
        demo_dir = manager.provision(multirepo=multirepo)

        console.print(f"📂 Created demo project at: [bold]{demo_dir}[/bold]")

        # Initialize inside the new demo directory
        _init_project(
            demo_dir, force=True, is_demo=True, telemetry_opt_in=True, pack_name=pack_name
        )

        console.print("\n[bold green]Ready to go! Try these commands:[/bold green]")
        console.print(f"1. cd {demo_dir.name}")
        console.print("2. [bold cyan]jnkn check[/bold cyan]")
        return

    # Standard initialization
    root_dir = Path.cwd()
    config_file = root_dir / ".jnkn" / "config.yaml"

    if config_file.exists() and not force:
        console.print(f"[yellow]Configuration already exists at {config_file}[/yellow]")
        if not Confirm.ask("Do you want to overwrite it?"):
            console.print("Aborted.")
            return

    _init_project(root_dir, force, telemetry_opt_in=telemetry, pack_name=pack_name)
