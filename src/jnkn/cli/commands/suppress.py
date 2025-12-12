"""
Suppress Commands - Manage match suppressions.

Allows you to suppress false positive matches that the stitcher creates.
"""

import json
from datetime import datetime, timedelta
from pathlib import Path

import click


@click.group()
def suppress():
    """Manage match suppressions.

    Suppressions prevent the stitcher from creating specific matches
    that you've identified as false positives.
    """
    pass


@suppress.command("add")
@click.argument("source_pattern")
@click.argument("target_pattern")
@click.option("-r", "--reason", default="", help="Reason for suppression")
@click.option("-u", "--created-by", default="cli", help="Who created this")
@click.option("-e", "--expires-days", type=int, help="Expires after N days")
@click.option(
    "--config", "config_path", default=".jnkn/suppressions.yaml", help="Path to suppressions file"
)
def suppress_add(
    source_pattern: str,
    target_pattern: str,
    reason: str,
    created_by: str,
    expires_days: int | None,
    config_path: str,
):
    """
    Add a new suppression rule.

    Patterns use glob syntax:
      * matches any characters
      ? matches single character

    \b
    Examples:
        jnkn suppress add "env:*_ID" "infra:*" -r "ID fields are generic"
        jnkn suppress add "env:HOST" "infra:*" -r "HOST is generic" -e 30
    """
    try:
        from ...stitching.suppressions import SuppressionStore

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

    except ImportError:
        _fallback_add(config_path, source_pattern, target_pattern, reason)


@suppress.command("remove")
@click.argument("identifier")
@click.option(
    "--config", "config_path", default=".jnkn/suppressions.yaml", help="Path to suppressions file"
)
def suppress_remove(identifier: str, config_path: str):
    """
    Remove a suppression by ID or index.

    \b
    Examples:
        jnkn suppress remove abc123
        jnkn suppress remove 1
    """
    try:
        from ...stitching.suppressions import SuppressionStore

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

    except ImportError:
        click.echo("❌ Suppression management requires stitching module")


@suppress.command("list")
@click.option(
    "--config", "config_path", default=".jnkn/suppressions.yaml", help="Path to suppressions file"
)
@click.option("--include-expired", is_flag=True, help="Include expired suppressions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def suppress_list(config_path: str, include_expired: bool, as_json: bool):
    """
    List all suppressions.

    \b
    Examples:
        jnkn suppress list
        jnkn suppress list --include-expired
        jnkn suppress list --json
    """
    try:
        from ...stitching.suppressions import SuppressionStore

        store = SuppressionStore(Path(config_path))
        store.load()
        suppressions = store.list(include_expired=include_expired)

        if as_json:
            data = [s.to_dict() for s in suppressions]
            click.echo(json.dumps(data, indent=2, default=str))
            return

        if not suppressions:
            click.echo("No suppressions configured.")
            click.echo()
            click.echo("Add one with:")
            click.echo('  jnkn suppress add "env:*_ID" "infra:*" -r "ID fields are generic"')
            return

        click.echo(f"📋 Suppressions ({len(suppressions)} total)")
        click.echo("=" * 60)

        for i, s in enumerate(suppressions, 1):
            status = ""
            if s.is_expired():
                status = " [EXPIRED]"
            elif not s.enabled:
                status = " [DISABLED]"

            click.echo()
            click.echo(f"#{i} (ID: {s.id}){status}")
            click.echo(f"   Pattern: {s.source_pattern} -> {s.target_pattern}")
            if s.reason:
                click.echo(f"   Reason: {s.reason}")
            click.echo(f"   Created: {s.created_at.strftime('%Y-%m-%d')} by {s.created_by}")
            if s.expires_at:
                click.echo(f"   Expires: {s.expires_at.strftime('%Y-%m-%d')}")

    except ImportError:
        _fallback_list(config_path)


@suppress.command("test")
@click.argument("source_id")
@click.argument("target_id")
@click.option(
    "--config", "config_path", default=".jnkn/suppressions.yaml", help="Path to suppressions file"
)
def suppress_test(source_id: str, target_id: str, config_path: str):
    """
    Test if a source/target pair would be suppressed.

    \b
    Examples:
        jnkn suppress test env:USER_ID infra:main
    """
    try:
        from ...stitching.suppressions import SuppressionStore

        store = SuppressionStore(Path(config_path))
        store.load()
        match = store.is_suppressed(source_id, target_id)

        if match.suppressed:
            click.echo(f"✓ SUPPRESSED: {source_id} -> {target_id}")
            if match.suppression:
                click.echo(
                    f"  By: {match.suppression.source_pattern} -> {match.suppression.target_pattern}"
                )
            if match.reason:
                click.echo(f"  Reason: {match.reason}")
        else:
            click.echo(f"✗ NOT suppressed: {source_id} -> {target_id}")

    except ImportError:
        click.echo("❌ Suppression testing requires stitching module")


# =============================================================================
# Fallback implementations (when stitching module not available)
# =============================================================================


def _fallback_add(config_path: str, source: str, target: str, reason: str):
    """Add suppression using basic YAML."""
    import yaml

    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    suppressions = []
    if path.exists():
        with open(path) as f:
            data = yaml.safe_load(f) or {}
            suppressions = data.get("suppressions", [])

    suppressions.append(
        {
            "source_pattern": source,
            "target_pattern": target,
            "reason": reason,
            "created_at": datetime.utcnow().isoformat(),
        }
    )

    with open(path, "w") as f:
        yaml.dump({"suppressions": suppressions}, f)

    click.echo("✅ Added suppression")
    click.echo(f"   Source: {source}")
    click.echo(f"   Target: {target}")


def _fallback_list(config_path: str):
    """List suppressions using basic YAML."""
    import yaml

    path = Path(config_path)
    if not path.exists():
        click.echo("No suppressions configured.")
        return

    with open(path) as f:
        data = yaml.safe_load(f) or {}

    suppressions = data.get("suppressions", [])

    if not suppressions:
        click.echo("No suppressions configured.")
        return

    click.echo(f"📋 Suppressions ({len(suppressions)} total)")
    click.echo("=" * 60)

    for i, s in enumerate(suppressions, 1):
        click.echo()
        click.echo(f"#{i}")
        click.echo(f"   Pattern: {s.get('source_pattern')} -> {s.get('target_pattern')}")
        if s.get("reason"):
            click.echo(f"   Reason: {s.get('reason')}")
