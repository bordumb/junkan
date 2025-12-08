"""
Junkan CLI.

Provides command-line interface for:
- scan: Parse codebase and build dependency graph
- blast-radius: Calculate impact of changes
- explain: Show why matches were made
- suppress: Manage false positive suppressions
- stats: Show graph statistics
"""

import click
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Set, Optional

from ..core.types import Node, Edge, NodeType
from ..analysis.explain import create_explanation_generator
from ..stitching.suppressions import SuppressionStore, create_default_store


# Skip these directories during scanning
SKIP_DIRS: Set[str] = {
    ".git", ".junkan", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
}


@click.group()
def main():
    """Junkan: Pre-Flight Impact Analysis Engine."""
    pass


@main.command()
@click.option("--dir", "scan_dir", default=".", help="Codebase root to scan")
@click.option("--db", default=".junkan/junkan.db", help="Path to SQLite DB")
@click.option("--full", is_flag=True, help="Force full rescan (ignore cache)")
@click.option("--min-confidence", default=0.5, help="Minimum stitching confidence")
def scan(scan_dir: str, db: str, full: bool, min_confidence: float):
    """
    Scan codebase and build dependency graph.
    
    Supports incremental scanning - only re-parses changed files.
    """
    click.echo(f"🚀 Scanning {Path(scan_dir).absolute()} ...")
    click.echo(f"   Database: {db}")
    click.echo(f"   Min confidence: {min_confidence}")
    click.echo("")
    click.echo("⚠️  Full scan implementation requires tree-sitter integration.")
    click.echo("   This CLI module provides the explain and suppress commands.")


@main.command("blast-radius")
@click.argument("artifacts", nargs=-1)
@click.option("--db", default=".junkan/junkan.db", help="Path to SQLite DB")
@click.option("--max-depth", default=-1, help="Maximum traversal depth")
@click.option("--lazy", is_flag=True, help="Use lazy SQL queries instead of loading graph")
def blast_radius(artifacts, db: str, max_depth: int, lazy: bool):
    """
    Calculate downstream impact for changed artifacts.
    
    Examples:
        junkan blast-radius env:DB_HOST
        junkan blast-radius src/models.py
        junkan blast-radius infra:payment_db
    """
    if not artifacts:
        click.echo("❌ Please provide at least one artifact to analyze.")
        click.echo("Examples:")
        click.echo("  junkan blast-radius env:DB_HOST")
        click.echo("  junkan blast-radius src/models.py")
        return
    
    click.echo(f"📊 Calculating blast radius for: {artifacts}")
    click.echo("⚠️  Full implementation requires storage adapter.")


@main.command()
@click.argument("source_id")
@click.argument("target_id")
@click.option("--db", default=".junkan/junkan.db", help="Path to SQLite DB")
@click.option("--min-confidence", default=0.5, help="Minimum confidence threshold")
@click.option("--why-not", is_flag=True, help="Explain why match was NOT made")
@click.option("--alternatives", is_flag=True, help="Show alternative matches")
def explain(
    source_id: str,
    target_id: str,
    db: str,
    min_confidence: float,
    why_not: bool,
    alternatives: bool,
):
    """
    Explain why a match was made (or not made).
    
    Examples:
        junkan explain env:PAYMENT_DB_HOST infra:payment_db_host
        junkan explain env:HOST infra:main --why-not
    """
    generator = create_explanation_generator(min_confidence=min_confidence)
    
    if why_not:
        output = generator.explain_why_not(source_id, target_id)
    else:
        explanation = generator.explain(
            source_id, target_id,
            find_alternatives=alternatives
        )
        output = generator.format(explanation)
    
    click.echo(output)


@main.group()
def suppress():
    """Manage match suppressions."""
    pass


@suppress.command("add")
@click.argument("source_pattern")
@click.argument("target_pattern")
@click.option("--reason", "-r", default="", help="Reason for suppression")
@click.option("--created-by", "-u", default="cli", help="Who created this suppression")
@click.option("--expires-days", "-e", type=int, help="Expires after N days")
@click.option("--config", "config_path", default=".junkan/suppressions.yaml", help="Path to suppressions file")
def suppress_add(
    source_pattern: str,
    target_pattern: str,
    reason: str,
    created_by: str,
    expires_days: Optional[int],
    config_path: str,
):
    """
    Add a new suppression rule.
    
    Patterns use glob syntax:
        * matches any characters
        ? matches single character
        [abc] matches a, b, or c
    
    Examples:
        junkan suppress add "env:*_ID" "infra:*" -r "ID fields are too generic"
        junkan suppress add "env:HOST" "infra:*" -r "HOST is generic" -e 30
    """
    store = SuppressionStore(Path(config_path))
    store.load()
    
    expires_at = None
    if expires_days:
        expires_at = datetime.utcnow() + timedelta(days=expires_days)
    
    suppression = store.add(
        source_pattern=source_pattern,
        target_pattern=target_pattern,
        reason=reason,
        created_by=created_by,
        expires_at=expires_at,
    )
    
    store.save()
    
    click.echo(f"✅ Added suppression (ID: {suppression.id})")
    click.echo(f"   Source: {source_pattern}")
    click.echo(f"   Target: {target_pattern}")
    if reason:
        click.echo(f"   Reason: {reason}")
    if expires_at:
        click.echo(f"   Expires: {expires_at.isoformat()}")


@suppress.command("remove")
@click.argument("identifier")
@click.option("--config", "config_path", default=".junkan/suppressions.yaml", help="Path to suppressions file")
def suppress_remove(identifier: str, config_path: str):
    """
    Remove a suppression by ID or index.
    
    Examples:
        junkan suppress remove abc123
        junkan suppress remove 1
    """
    store = SuppressionStore(Path(config_path))
    store.load()
    
    # Try as index first
    try:
        index = int(identifier)
        if store.remove_by_index(index):
            store.save()
            click.echo(f"✅ Removed suppression #{index}")
            return
        else:
            click.echo(f"❌ No suppression at index {index}")
            return
    except ValueError:
        pass
    
    # Try as ID
    if store.remove(identifier):
        store.save()
        click.echo(f"✅ Removed suppression {identifier}")
    else:
        click.echo(f"❌ Suppression not found: {identifier}")


@suppress.command("list")
@click.option("--config", "config_path", default=".junkan/suppressions.yaml", help="Path to suppressions file")
@click.option("--include-expired", is_flag=True, help="Include expired suppressions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def suppress_list(config_path: str, include_expired: bool, as_json: bool):
    """
    List all suppressions.
    
    Examples:
        junkan suppress list
        junkan suppress list --include-expired
        junkan suppress list --json
    """
    store = SuppressionStore(Path(config_path))
    store.load()
    suppressions = store.list(include_expired=include_expired)
    
    if as_json:
        data = [s.to_dict() for s in suppressions]
        click.echo(json.dumps(data, indent=2, default=str))
        return
    
    if not suppressions:
        click.echo("No suppressions configured.")
        click.echo("")
        click.echo("Add one with:")
        click.echo('  junkan suppress add "env:*_ID" "infra:*" -r "ID fields are generic"')
        return
    
    click.echo(f"📋 Suppressions ({len(suppressions)} total)")
    click.echo("=" * 60)
    
    for i, s in enumerate(suppressions, 1):
        status = ""
        if s.is_expired():
            status = " [EXPIRED]"
        elif not s.enabled:
            status = " [DISABLED]"
        
        click.echo(f"\n#{i} (ID: {s.id}){status}")
        click.echo(f"   Pattern: {s.source_pattern} -> {s.target_pattern}")
        if s.reason:
            click.echo(f"   Reason: {s.reason}")
        click.echo(f"   Created: {s.created_at.strftime('%Y-%m-%d')} by {s.created_by}")
        if s.expires_at:
            click.echo(f"   Expires: {s.expires_at.strftime('%Y-%m-%d')}")


@suppress.command("test")
@click.argument("source_id")
@click.argument("target_id")
@click.option("--config", "config_path", default=".junkan/suppressions.yaml", help="Path to suppressions file")
def suppress_test(source_id: str, target_id: str, config_path: str):
    """
    Test if a source/target pair would be suppressed.
    
    Examples:
        junkan suppress test env:USER_ID infra:main
    """
    store = SuppressionStore(Path(config_path))
    store.load()
    match = store.is_suppressed(source_id, target_id)
    
    if match.suppressed:
        click.echo(f"✓ SUPPRESSED: {source_id} -> {target_id}")
        if match.suppression:
            click.echo(f"  By pattern: {match.suppression.source_pattern} -> {match.suppression.target_pattern}")
        if match.reason:
            click.echo(f"  Reason: {match.reason}")
    else:
        click.echo(f"✗ NOT suppressed: {source_id} -> {target_id}")


@main.command()
@click.option("--db", default=".junkan/junkan.db", help="Path to SQLite DB")
def stats(db: str):
    """Show graph statistics."""
    db_path = Path(db)
    
    if not db_path.exists():
        click.echo(f"❌ Database not found: {db}")
        click.echo("Run 'junkan scan' first to create the database.")
        return
    
    click.echo("📊 Graph Statistics")
    click.echo("=" * 40)
    click.echo(f"Database: {db}")
    click.echo(f"DB Size: {db_path.stat().st_size / 1024:.1f} KB")
    click.echo("")
    click.echo("⚠️  Full stats require storage adapter implementation.")


@main.command()
@click.option("--db", default=".junkan/junkan.db", help="Path to SQLite DB")
@click.confirmation_option(prompt="Are you sure you want to clear all data?")
def clear(db: str):
    """Clear all data from the database."""
    db_path = Path(db)
    
    if db_path.exists():
        db_path.unlink()
        click.echo("✅ Database cleared.")
    else:
        click.echo("Database does not exist.")


@main.command()
def version():
    """Show Junkan version."""
    from .. import __version__
    click.echo(f"Junkan v{__version__}")


if __name__ == "__main__":
    main()