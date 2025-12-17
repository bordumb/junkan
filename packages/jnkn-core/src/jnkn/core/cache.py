"""
Cache Manager for Git Dependencies.

Provides management utilities for the git dependency cache, including
listing, cleaning, and invalidating cached repositories.

Cache Location:
    ~/.jnkn/cache/

Commands:
    - list: Show all cached repositories with sizes and ages
    - clean: Remove old or unused caches
    - invalidate: Force re-fetch of specific dependency
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .git_fetcher import GitFetcher

logger = logging.getLogger(__name__)


@dataclass
class CacheStats:
    """
    Statistics about the git dependency cache.

    Attributes:
        total_repos: Number of cached repositories.
        total_size_bytes: Total size in bytes.
        oldest_update: Timestamp of oldest cache entry.
        newest_update: Timestamp of newest cache entry.
    """

    total_repos: int
    total_size_bytes: int
    oldest_update: Optional[datetime] = None
    newest_update: Optional[datetime] = None

    @property
    def total_size_mb(self) -> float:
        """Get total size in megabytes."""
        return round(self.total_size_bytes / (1024 * 1024), 2)

    @property
    def total_size_human(self) -> str:
        """Get human-readable size string."""
        size = self.total_size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


@dataclass
class CacheItem:
    """
    Information about a single cached repository.

    Attributes:
        name: Dependency name.
        path: Path to cached repository.
        git_url: Original repository URL.
        current_sha: Currently checked-out commit.
        last_updated: When the cache was last updated.
        size_bytes: Size of the cached repository.
        age_days: Days since last update.
    """

    name: str
    path: Path
    git_url: str
    current_sha: str
    last_updated: datetime
    size_bytes: int
    age_days: int

    @property
    def size_human(self) -> str:
        """Get human-readable size string."""
        size = self.size_bytes
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def short_sha(self) -> str:
        """Get shortened SHA (8 chars)."""
        return self.current_sha[:8] if self.current_sha else "unknown"

    @property
    def age_human(self) -> str:
        """Get human-readable age string."""
        if self.age_days == 0:
            return "today"
        elif self.age_days == 1:
            return "yesterday"
        elif self.age_days < 7:
            return f"{self.age_days} days ago"
        elif self.age_days < 30:
            weeks = self.age_days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif self.age_days < 365:
            months = self.age_days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = self.age_days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"


class CacheManager:
    """
    Manages the git dependency cache.

    Provides utilities for listing, cleaning, and managing cached
    git repositories used by jnkn's dependency resolution.

    Example:
        ```python
        manager = CacheManager()

        # List all cached repos
        for item in manager.list():
            print(f"{item.name}: {item.size_human}, {item.age_human}")

        # Clean old caches
        removed = manager.clean(older_than_days=30)
        print(f"Removed {len(removed)} old caches")
        ```
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize cache manager.

        Args:
            cache_dir: Override default cache directory.
        """
        self.fetcher = GitFetcher(cache_dir)
        self.cache_dir = self.fetcher.cache_dir

    def list(self) -> List[CacheItem]:
        """
        List all cached repositories.

        Returns:
            List of CacheItem objects sorted by name.
        """
        items = []
        now = datetime.now(timezone.utc)

        for entry in self.fetcher.list_cached():
            cache_path = self.cache_dir / entry.name

            # Calculate age in days
            age = now - entry.last_updated
            age_days = age.days

            items.append(
                CacheItem(
                    name=entry.name,
                    path=cache_path,
                    git_url=entry.git_url,
                    current_sha=entry.current_sha,
                    last_updated=entry.last_updated,
                    size_bytes=entry.size_bytes,
                    age_days=age_days,
                )
            )

        return sorted(items, key=lambda x: x.name)

    def get_stats(self) -> CacheStats:
        """
        Get overall cache statistics.

        Returns:
            CacheStats object with aggregate information.
        """
        entries = self.fetcher.list_cached()

        if not entries:
            return CacheStats(total_repos=0, total_size_bytes=0)

        total_size = sum(e.size_bytes for e in entries)
        dates = [e.last_updated for e in entries]

        return CacheStats(
            total_repos=len(entries),
            total_size_bytes=total_size,
            oldest_update=min(dates) if dates else None,
            newest_update=max(dates) if dates else None,
        )

    def get_item(self, name: str) -> Optional[CacheItem]:
        """
        Get information about a specific cached repository.

        Args:
            name: Dependency name.

        Returns:
            CacheItem if cached, None otherwise.
        """
        items = self.list()
        for item in items:
            if item.name == name:
                return item
        return None

    def clean(
        self,
        older_than_days: Optional[int] = None,
        larger_than_mb: Optional[float] = None,
        dry_run: bool = False,
    ) -> List[str]:
        """
        Clean old or large caches.

        Args:
            older_than_days: Remove caches older than this many days.
            larger_than_mb: Remove caches larger than this size in MB.
            dry_run: If True, don't actually remove, just return what would be removed.

        Returns:
            List of dependency names that were (or would be) removed.
        """
        items = self.list()
        to_remove = []

        for item in items:
            remove = False

            if older_than_days is not None and item.age_days > older_than_days:
                remove = True

            if larger_than_mb is not None:
                size_mb = item.size_bytes / (1024 * 1024)
                if size_mb > larger_than_mb:
                    remove = True

            if remove:
                to_remove.append(item.name)

        if not dry_run:
            for name in to_remove:
                self.invalidate(name)

        return to_remove

    def invalidate(self, name: str) -> bool:
        """
        Remove a specific cached repository.

        Args:
            name: Dependency name.

        Returns:
            True if removed, False if not found.
        """
        return self.fetcher.invalidate(name)

    def invalidate_all(self) -> int:
        """
        Remove all cached repositories.

        Returns:
            Number of repositories removed.
        """
        items = self.list()
        count = 0

        for item in items:
            if self.invalidate(item.name):
                count += 1

        return count

    def verify_integrity(self) -> List[str]:
        """
        Check cache integrity and report issues.

        Returns:
            List of issue descriptions.
        """
        issues = []

        for item in self.list():
            # Check if .git directory exists
            git_dir = item.path / ".git"
            if not git_dir.exists():
                issues.append(f"{item.name}: Missing .git directory")
                continue

            # Try to get HEAD SHA
            try:
                sha = self.fetcher.get_current_sha(item.path)
                if sha != item.current_sha:
                    issues.append(
                        f"{item.name}: SHA mismatch (cached: {item.short_sha}, actual: {sha[:8]})"
                    )
            except Exception as e:
                issues.append(f"{item.name}: Cannot read HEAD ({e})")

        return issues


def get_cache_dir() -> Path:
    """Get the default cache directory path."""
    return GitFetcher.CACHE_DIR


def format_cache_list(items: List[CacheItem], verbose: bool = False) -> str:
    """
    Format cache list for CLI output.

    Args:
        items: List of CacheItem objects.
        verbose: Include detailed information.

    Returns:
        Formatted string for display.
    """
    if not items:
        return "Cache is empty."

    lines = []
    max_name_len = max(len(item.name) for item in items)

    for item in items:
        name_col = item.name.ljust(max_name_len)
        size_col = item.size_human.rjust(10)
        age_col = item.age_human
        sha_col = item.short_sha

        if verbose:
            lines.append(f"{name_col}  {size_col}  {age_col:15}  {sha_col}")
        else:
            lines.append(f"{name_col}  {size_col}  {age_col}")

    return "\n".join(lines)
