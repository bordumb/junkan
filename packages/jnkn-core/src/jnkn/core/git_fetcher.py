"""
Git Repository Fetcher.

Handles cloning, caching, and updating of remote git repositories for
multi-repository dependency resolution.

Cache Structure:
    ~/.jnkn/cache/
    ├── <dep-name>/           # Cloned repository
    │   ├── .git/
    │   └── ...
    └── .cache_meta.json      # Metadata about cached repos
"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from .manifest import DependencySpec, GitSpec

logger = logging.getLogger(__name__)


class GitFetchError(Exception):
    """
    Raised when a git operation fails.

    Attributes:
        message: Human-readable error message.
        stderr: Raw stderr output from git command.
    """

    def __init__(self, message: str, stderr: str = ""):
        self.message = message
        self.stderr = stderr
        super().__init__(f"{message}: {stderr}" if stderr else message)


@dataclass
class CacheEntry:
    """
    Metadata about a cached repository.

    Attributes:
        name: Dependency name.
        git_url: Repository URL.
        current_sha: Currently checked-out commit SHA.
        last_updated: Timestamp of last fetch/clone.
        size_bytes: Approximate size of cached repo.
    """

    name: str
    git_url: str
    current_sha: str
    last_updated: datetime
    size_bytes: int = 0

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "git_url": self.git_url,
            "current_sha": self.current_sha,
            "last_updated": self.last_updated.isoformat(),
            "size_bytes": self.size_bytes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CacheEntry":
        """Deserialize from dictionary."""
        last_updated = data.get("last_updated")
        if isinstance(last_updated, str):
            last_updated = datetime.fromisoformat(last_updated.replace("Z", "+00:00"))
        else:
            last_updated = datetime.now(timezone.utc)

        return cls(
            name=data["name"],
            git_url=data["git_url"],
            current_sha=data["current_sha"],
            last_updated=last_updated,
            size_bytes=data.get("size_bytes", 0),
        )


class GitFetcher:
    """
    Fetches and caches Git repositories.

    Implements shallow cloning for performance and supports both HTTPS
    and SSH repository URLs. Uses git credential helpers for authentication.

    Attributes:
        cache_dir: Directory for storing cloned repositories.
    """

    CACHE_DIR = Path.home() / ".jnkn" / "cache"
    META_FILE = ".cache_meta.json"

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize the git fetcher.

        Args:
            cache_dir: Override default cache directory.
        """
        self.cache_dir = cache_dir or self.CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._meta: dict[str, CacheEntry] = {}
        self._load_meta()

    def _load_meta(self) -> None:
        """Load cache metadata from disk."""
        meta_path = self.cache_dir / self.META_FILE
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    data = json.load(f)
                self._meta = {
                    name: CacheEntry.from_dict(entry)
                    for name, entry in data.get("entries", {}).items()
                }
            except Exception as e:
                logger.warning(f"Failed to load cache metadata: {e}")
                self._meta = {}

    def _save_meta(self) -> None:
        """Save cache metadata to disk."""
        meta_path = self.cache_dir / self.META_FILE
        data = {"entries": {name: entry.to_dict() for name, entry in self._meta.items()}}
        with open(meta_path, "w") as f:
            json.dump(data, f, indent=2)

    def _run_git(self, *args: str, cwd: Optional[Path] = None) -> str:
        """
        Run a git command and return stdout.

        Args:
            *args: Git command arguments.
            cwd: Working directory for the command.

        Returns:
            Stdout output stripped of whitespace.

        Raises:
            GitFetchError: If the command fails.
        """
        cmd = ["git"] + list(args)
        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,  # 5 minute timeout for large repos
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise GitFetchError(f"Git command failed: {' '.join(args)}", e.stderr.strip())
        except subprocess.TimeoutExpired:
            raise GitFetchError(f"Git command timed out: {' '.join(args)}")

    def fetch(self, name: str, spec: DependencySpec) -> Path:
        """
        Clone or update a Git repository.

        Args:
            name: Dependency name (used as cache directory name).
            spec: Dependency specification with git URL and ref.

        Returns:
            Path to the cached repository.

        Raises:
            GitFetchError: If cloning or checkout fails.
        """
        git_spec = spec.as_git_spec()
        if not git_spec:
            raise GitFetchError(f"Dependency '{name}' has no git URL")

        cache_path = self.cache_dir / name
        ref = git_spec.get_ref()

        if cache_path.exists():
            # Update existing clone - re-clone if branch changed
            self._update_or_reclone(cache_path, git_spec, name)
        else:
            # Fresh clone with specific branch
            self._clone_repo(git_spec.git, cache_path, ref)

        # Update metadata
        sha = self.get_current_sha(cache_path)
        self._meta[name] = CacheEntry(
            name=name,
            git_url=git_spec.git,
            current_sha=sha,
            last_updated=datetime.now(timezone.utc),
            size_bytes=self._get_dir_size(cache_path),
        )
        self._save_meta()

        return cache_path

    def _clone_repo(self, url: str, dest: Path, ref: str = "main") -> None:
        """
        Perform shallow clone with specific branch.

        Args:
            url: Repository URL.
            dest: Destination path.
            ref: Branch, tag, or commit to checkout.
        """
        logger.info(f"🌐 Cloning {url} (ref: {ref})...")

        try:
            # Try cloning with specific branch
            self._run_git(
                "clone",
                "--depth",
                "1",
                "--branch",
                ref,
                "--single-branch",
                url,
                str(dest),
            )
        except GitFetchError as e:
            # If branch doesn't exist, clone default and then checkout
            if "not found" in e.stderr.lower() or "could not find" in e.stderr.lower():
                logger.debug(f"Branch {ref} not found, trying default clone")
                self._run_git(
                    "clone",
                    "--depth",
                    "1",
                    url,
                    str(dest),
                )
                # Then try to fetch and checkout the specific ref
                self._fetch_and_checkout(dest, ref)
            else:
                raise

    def _update_or_reclone(self, repo: Path, spec: GitSpec, name: str) -> None:
        """
        Update repository or re-clone if branch changed.

        Args:
            repo: Path to repository.
            spec: Git specification with ref info.
            name: Dependency name.
        """
        ref = spec.get_ref()

        # Check current branch
        try:
            current_branch = self._run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)
        except GitFetchError:
            current_branch = None

        # If we need a different branch, re-clone
        if current_branch != ref and spec.branch:
            logger.info(f"Branch changed from {current_branch} to {ref}, re-cloning...")
            shutil.rmtree(repo)
            self._clone_repo(spec.git, repo, ref)
            return

        # Otherwise, just fetch updates
        logger.debug(f"Updating repository at {repo}")
        try:
            self._run_git("fetch", "--depth", "1", "origin", ref, cwd=repo)
            self._run_git("reset", "--hard", "origin/" + ref, cwd=repo)
        except GitFetchError as e:
            logger.warning(f"Update failed: {e}")
            # Re-clone if update fails
            logger.info("Re-cloning due to update failure...")
            shutil.rmtree(repo)
            self._clone_repo(spec.git, repo, ref)

    def _fetch_and_checkout(self, repo: Path, ref: str) -> None:
        """
        Fetch a specific ref and checkout.

        Args:
            repo: Path to repository.
            ref: Branch, tag, or SHA to checkout.
        """
        try:
            # Fetch the specific ref
            self._run_git("fetch", "origin", ref, "--depth", "1", cwd=repo)
            # Checkout using FETCH_HEAD
            self._run_git("checkout", "FETCH_HEAD", cwd=repo)
        except GitFetchError:
            # If that fails, try checking out directly (for tags/SHAs)
            self._run_git("checkout", ref, cwd=repo)

    def get_current_sha(self, repo: Path) -> str:
        """
        Get the current HEAD SHA.

        Args:
            repo: Path to repository.

        Returns:
            Full commit SHA string.
        """
        return self._run_git("rev-parse", "HEAD", cwd=repo)

    def get_cached_path(self, name: str) -> Optional[Path]:
        """
        Get path to cached repository if it exists.

        Args:
            name: Dependency name.

        Returns:
            Path if cached, None otherwise.
        """
        cache_path = self.cache_dir / name
        if cache_path.exists() and (cache_path / ".git").exists():
            return cache_path
        return None

    def is_cached(self, name: str) -> bool:
        """Check if a dependency is cached."""
        return self.get_cached_path(name) is not None

    def invalidate(self, name: str) -> bool:
        """
        Remove a cached repository.

        Args:
            name: Dependency name.

        Returns:
            True if cache was removed, False if not found.
        """
        cache_path = self.cache_dir / name
        if cache_path.exists():
            shutil.rmtree(cache_path)
            if name in self._meta:
                del self._meta[name]
                self._save_meta()
            return True
        return False

    def clean_old_caches(self, max_age_days: int = 30) -> List[str]:
        """
        Remove caches older than specified age.

        Args:
            max_age_days: Maximum age in days before removal.

        Returns:
            List of removed dependency names.
        """
        from datetime import timedelta

        removed = []
        cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

        for name, entry in list(self._meta.items()):
            if entry.last_updated < cutoff:
                if self.invalidate(name):
                    removed.append(name)

        return removed

    def list_cached(self) -> List[CacheEntry]:
        """
        List all cached repositories.

        Returns:
            List of CacheEntry objects.
        """
        return list(self._meta.values())

    def get_cache_stats(self) -> dict:
        """
        Get statistics about the cache.

        Returns:
            Dictionary with cache statistics.
        """
        total_size = sum(e.size_bytes for e in self._meta.values())
        return {
            "count": len(self._meta),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
        }

    @staticmethod
    def _get_dir_size(path: Path) -> int:
        """Get approximate size of directory in bytes."""
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception:
            pass
        return total
