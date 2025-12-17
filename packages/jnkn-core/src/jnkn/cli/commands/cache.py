"""
Cache CLI Command.

Manage the git dependency cache for remote repositories.

Usage:
    jnkn cache list [-v]
    jnkn cache clean [--older-than DAYS] [--dry-run]
    jnkn cache invalidate <name>
    jnkn cache stats
"""

import click

from ...core.cache import CacheManager, format_cache_list


@click.group()
def cache():
    """Manage git dependency cache."""
    pass


@cache.command("list")
@click.option("-v", "--verbose", is_flag=True, help="Show detailed information including SHA")
def cache_list(verbose: bool):
    """List all cached repositories."""
    manager = CacheManager()
    items = manager.list()

    if not items:
        click.echo("📦 Cache is empty.")
        return

    click.echo(f"📦 Cached repositories ({len(items)}):\n")
    click.echo(format_cache_list(items, verbose=verbose))


@cache.command("stats")
def cache_stats():
    """Show cache statistics."""
    manager = CacheManager()
    stats = manager.get_stats()

    click.echo("📊 Cache Statistics:\n")
    click.echo(f"   Total repositories: {stats.total_repos}")
    click.echo(f"   Total size: {stats.total_size_human}")

    if stats.oldest_update:
        click.echo(f"   Oldest update: {stats.oldest_update.strftime('%Y-%m-%d %H:%M')}")
    if stats.newest_update:
        click.echo(f"   Newest update: {stats.newest_update.strftime('%Y-%m-%d %H:%M')}")


@cache.command("clean")
@click.option("--older-than", type=int, help="Remove caches older than N days")
@click.option("--larger-than", type=float, help="Remove caches larger than N MB")
@click.option("--dry-run", is_flag=True, help="Show what would be removed without removing")
def cache_clean(older_than: int | None, larger_than: float | None, dry_run: bool):
    """Clean old or large cached repositories."""
    if not older_than and not larger_than:
        click.echo("Specify --older-than or --larger-than to clean caches.")
        return

    manager = CacheManager()
    removed = manager.clean(
        older_than_days=older_than,
        larger_than_mb=larger_than,
        dry_run=dry_run,
    )

    if not removed:
        click.echo("✅ No caches match the criteria.")
        return

    action = "Would remove" if dry_run else "Removed"
    click.echo(f"🗑️  {action} {len(removed)} cache(s):")
    for name in removed:
        click.echo(f"   - {name}")


@cache.command("invalidate")
@click.argument("name")
def cache_invalidate(name: str):
    """Remove a specific cached repository."""
    manager = CacheManager()

    if manager.invalidate(name):
        click.echo(f"✅ Invalidated cache: {name}")
    else:
        click.echo(f"❌ Cache not found: {name}")


@cache.command("verify")
def cache_verify():
    """Verify cache integrity."""
    manager = CacheManager()
    issues = manager.verify_integrity()

    if not issues:
        click.echo("✅ All caches are valid.")
        return

    click.echo(f"⚠️  Found {len(issues)} issue(s):\n")
    for issue in issues:
        click.echo(f"   - {issue}")
