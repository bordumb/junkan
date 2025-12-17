"""
Mappings CLI Command.

Manage explicit mappings between artifacts in the dependency graph.

Usage:
    jnkn mappings list
    jnkn mappings validate
    jnkn mappings suggest
"""

from pathlib import Path

import click

from ...core.manifest import MappingType, ProjectManifest
from ...core.mappings import (
    MappingValidator,
    suggest_mappings,
)
from ...core.storage.sqlite import SQLiteStorage


@click.group()
def mappings():
    """Manage explicit artifact mappings."""
    pass


@mappings.command("list")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed information")
def mappings_list(verbose: bool):
    """List all explicit mappings from jnkn.toml."""
    project_root = Path.cwd()
    manifest_path = project_root / "jnkn.toml"

    if not manifest_path.exists():
        click.echo("❌ No jnkn.toml found in current directory.")
        return

    manifest = ProjectManifest.load(manifest_path)

    if not manifest.mappings:
        click.echo("📋 No explicit mappings defined.")
        click.echo("\nAdd mappings to jnkn.toml:")
        click.echo("  [mappings]")
        click.echo('  "infra:output:db_url" = "env:DATABASE_URL"')
        return

    click.echo(f"📋 Explicit Mappings ({len(manifest.mappings)}):\n")

    provides_count = 0
    ignore_count = 0

    for mapping in manifest.mappings:
        if mapping.mapping_type == MappingType.IGNORE:
            ignore_count += 1
            icon = "🚫"
            if verbose:
                reason = f" ({mapping.reason})" if mapping.reason else ""
                click.echo(f"  {icon} {mapping.source} → IGNORED{reason}")
            else:
                click.echo(f"  {icon} {mapping.source} → IGNORED")
        else:
            provides_count += 1
            icon = "🔗"
            if verbose:
                reason = f" ({mapping.reason})" if mapping.reason else ""
                click.echo(f"  {icon} {mapping.source} → {mapping.target}{reason}")
            else:
                click.echo(f"  {icon} {mapping.source} → {mapping.target}")

    click.echo(f"\n  Total: {provides_count} provides, {ignore_count} ignores")


@mappings.command("validate")
def mappings_validate():
    """Validate mappings against the current dependency graph."""
    project_root = Path.cwd()
    manifest_path = project_root / "jnkn.toml"
    db_path = project_root / ".jnkn" / "jnkn.db"

    if not manifest_path.exists():
        click.echo("❌ No jnkn.toml found.")
        return

    if not db_path.exists():
        click.echo("❌ No dependency graph found. Run 'jnkn scan' first.")
        return

    manifest = ProjectManifest.load(manifest_path)

    if not manifest.mappings:
        click.echo("✅ No mappings to validate.")
        return

    # Get node IDs from database
    storage = SQLiteStorage(db_path)
    nodes = storage.get_all_nodes()
    node_ids = {n.id for n in nodes}

    validator = MappingValidator(node_ids)
    warnings = validator.validate(manifest.mappings)

    if not warnings:
        click.echo("✅ All mappings are valid.")
        return

    click.echo(f"⚠️  Found {len(warnings)} issue(s):\n")

    for warning in warnings:
        icon = "❌" if warning.severity == "error" else "⚠️"
        click.echo(f"  {icon} {warning.message}")
        if warning.suggestion:
            click.echo(f"     💡 {warning.suggestion}")


@mappings.command("suggest")
@click.option("--min-confidence", type=float, default=0.5, help="Minimum confidence threshold")
def mappings_suggest(min_confidence: float):
    """Suggest mappings for orphaned nodes."""
    project_root = Path.cwd()
    db_path = project_root / ".jnkn" / "jnkn.db"

    if not db_path.exists():
        click.echo("❌ No dependency graph found. Run 'jnkn scan' first.")
        return

    storage = SQLiteStorage(db_path)
    nodes = storage.get_all_nodes()
    edges = storage.get_all_edges()

    # Find orphan env vars (no incoming 'provides' edge)
    target_ids_with_provides = {e.target_id for e in edges if e.type.value == "provides"}
    env_vars = [n for n in nodes if n.type.value == "env_var"]
    orphans = [n.id for n in env_vars if n.id not in target_ids_with_provides]

    if not orphans:
        click.echo("✅ No orphaned environment variables found.")
        return

    # Find potential infra sources
    infra_outputs = [n.id for n in nodes if "output" in n.id.lower()]

    suggestions = suggest_mappings(orphans, infra_outputs, min_confidence)

    if not suggestions:
        click.echo(f"🔍 Found {len(orphans)} orphans but no good matches.")
        click.echo("\nOrphaned variables:")
        for orphan in orphans[:10]:
            click.echo(f"  - {orphan}")
        return

    click.echo(f"💡 Suggested Mappings ({len(suggestions)}):\n")
    click.echo("Add to jnkn.toml [mappings] section:\n")

    for source, target, confidence in sorted(suggestions, key=lambda x: -x[2]):
        pct = int(confidence * 100)
        click.echo(f'  "{source}" = "{target}"  # {pct}% confidence')


@mappings.command("show-ignored")
def mappings_show_ignored():
    """Show all ignored source patterns."""
    project_root = Path.cwd()
    manifest_path = project_root / "jnkn.toml"

    if not manifest_path.exists():
        click.echo("❌ No jnkn.toml found.")
        return

    manifest = ProjectManifest.load(manifest_path)
    ignored = [m for m in manifest.mappings if m.mapping_type == MappingType.IGNORE]

    if not ignored:
        click.echo("📋 No ignored sources defined.")
        click.echo("\nTo ignore a source, add to jnkn.toml:")
        click.echo("  [mappings]")
        click.echo('  "env:CI_TOKEN" = { ignore = true, reason = "Injected by CI" }')
        return

    click.echo(f"🚫 Ignored Sources ({len(ignored)}):\n")

    for mapping in ignored:
        reason = f" - {mapping.reason}" if mapping.reason else ""
        click.echo(f"  {mapping.source}{reason}")
