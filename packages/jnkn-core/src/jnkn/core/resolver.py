"""
Dependency Resolver.

Responsible for resolving abstract dependencies declared in jnkn.toml
into concrete local filesystem paths.

Resolution Strategy:
    1. Local overrides ([tool.jnkn.sources]) - Highest priority
    2. Lockfile (if --frozen mode) - For reproducible builds
    3. Git remote - Clone and cache
    4. Local path - Direct filesystem reference

Phases:
    - Phase 1: Local path dependencies
    - Phase 2: Git remote dependencies with lockfile support
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from .git_fetcher import GitFetcher, GitFetchError
from .lockfile import LockedPackage, Lockfile, create_locked_package
from .manifest import (
    DependencySource,
    DependencySpec,
    ProjectManifest,
    ResolvedDependency,
)

logger = logging.getLogger(__name__)


class DependencyError(Exception):
    """
    Raised when dependency resolution fails.

    Attributes:
        dependency_name: Name of the dependency that failed.
        message: Human-readable error message.
    """

    def __init__(self, dependency_name: str, message: str):
        self.dependency_name = dependency_name
        self.message = message
        super().__init__(f"Dependency '{dependency_name}': {message}")


@dataclass
class ResolutionResult:
    """
    Result container for the resolution process.

    Attributes:
        dependencies: List of successfully resolved dependencies.
        warnings: Non-fatal warnings encountered during resolution.
        lockfile_stale: True if the lockfile needs updating.
        lockfile_updates: List of packages that need lockfile updates.
    """

    dependencies: List[ResolvedDependency] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    lockfile_stale: bool = False
    lockfile_updates: List[LockedPackage] = field(default_factory=list)

    def add_dependency(self, dep: ResolvedDependency) -> None:
        """Add a resolved dependency."""
        self.dependencies.append(dep)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    @property
    def success(self) -> bool:
        """Check if resolution was successful (has at least one dependency)."""
        return len(self.dependencies) > 0 or len(self.warnings) == 0


class DependencyResolver:
    """
    Resolves dependencies from manifest to concrete paths.

    Supports local path dependencies (Phase 1) and git remote dependencies
    (Phase 2) with lockfile pinning for reproducible builds.

    Attributes:
        project_root: Root directory containing jnkn.toml.
        frozen: If True, enforce lockfile versions strictly.
        offline: If True, only use cached dependencies.

    Example:
        ```python
        resolver = DependencyResolver(Path("./my-project"))
        result = resolver.resolve()
        for dep in result.dependencies:
            print(f"{dep.name}: {dep.path}")
        ```
    """

    def __init__(
        self,
        project_root: Path,
        frozen: bool = False,
        offline: bool = False,
    ):
        """
        Initialize the resolver.

        Args:
            project_root: The root directory containing jnkn.toml.
            frozen: Whether to enforce lockfile versions.
            offline: Whether to disable network calls.
        """
        self.project_root = project_root.resolve()
        self.frozen = frozen
        self.offline = offline
        self.git_fetcher = GitFetcher()

    def resolve(self) -> ResolutionResult:
        """
        Resolve all dependencies declared in the manifest.

        Returns:
            ResolutionResult containing list of resolved paths and any warnings.

        Raises:
            DependencyError: If a required dependency cannot be resolved.
        """
        manifest_path = self.project_root / "jnkn.toml"
        manifest = ProjectManifest.load(manifest_path)

        lockfile_path = self.project_root / "jnkn.lock"
        lockfile = Lockfile.load(lockfile_path)

        result = ResolutionResult()

        for name, spec in manifest.dependencies.items():
            try:
                dep = self._resolve_single(
                    name=name,
                    spec=spec,
                    overrides=manifest.source_overrides,
                    lockfile=lockfile,
                )
                result.add_dependency(dep)

                # Track lockfile staleness for git dependencies
                if dep.source in (DependencySource.GIT, DependencySource.GIT_LOCKED):
                    locked = lockfile.get_package(name)
                    if locked is None or locked.rev != dep.git_sha:
                        result.lockfile_stale = True
                        result.lockfile_updates.append(
                            create_locked_package(
                                name=name,
                                git_url=spec.git or "",
                                rev=dep.git_sha or "",
                                branch=spec.branch,
                                tag=spec.tag,
                            )
                        )

            except Exception as e:
                logger.error(f"Failed to resolve dependency '{name}': {e}")
                raise DependencyError(name, str(e))

        return result

    def _resolve_single(
        self,
        name: str,
        spec: DependencySpec,
        overrides: dict[str, DependencySpec],
        lockfile: Lockfile,
    ) -> ResolvedDependency:
        """
        Resolve a single dependency name.

        Resolution priority:
        1. Local override ([tool.jnkn.sources])
        2. Lockfile (if frozen mode)
        3. Git dependency
        4. Local path

        Args:
            name: Dependency name.
            spec: Dependency specification.
            overrides: Local path overrides.
            lockfile: Current lockfile state.

        Returns:
            ResolvedDependency with concrete path.

        Raises:
            DependencyError: If resolution fails.
        """
        # 1. Check local override (Highest priority)
        if name in overrides:
            override = overrides[name]
            if override.path:
                override_path = (self.project_root / override.path).resolve()
                if override_path.exists():
                    logger.info(f"📁 {name}: Using local override at {override_path}")
                    return ResolvedDependency(
                        name=name,
                        path=override_path,
                        source=DependencySource.LOCAL_OVERRIDE,
                    )
                else:
                    logger.warning(
                        f"Override path for '{name}' not found at {override_path}. "
                        "Falling back to standard resolution."
                    )

        # 2. Check lockfile (if frozen mode)
        if self.frozen:
            locked = lockfile.get_package(name)
            if locked and locked.rev:
                return self._resolve_from_lockfile(name, locked, spec)

        # 3. Git dependency
        if spec.git:
            return self._resolve_git(name, spec)

        # 4. Local path dependency
        if spec.path:
            return self._resolve_local(name, spec)

        raise DependencyError(name, "No valid source (path or git) specified")

    def _resolve_local(self, name: str, spec: DependencySpec) -> ResolvedDependency:
        """
        Resolve a local path dependency.

        Args:
            name: Dependency name.
            spec: Dependency specification.

        Returns:
            ResolvedDependency with local path.

        Raises:
            DependencyError: If path doesn't exist.
        """
        if not spec.path:
            raise DependencyError(name, "No path specified")

        local_path = (self.project_root / spec.path).resolve()
        if not local_path.exists():
            raise DependencyError(name, f"Path not found: {local_path}")

        logger.info(f"📁 {name}: Using local path {local_path}")
        return ResolvedDependency(
            name=name,
            path=local_path,
            source=DependencySource.LOCAL,
        )

    def _resolve_git(self, name: str, spec: DependencySpec) -> ResolvedDependency:
        """
        Resolve a git dependency by cloning/updating.

        Args:
            name: Dependency name.
            spec: Dependency specification.

        Returns:
            ResolvedDependency with cached path.

        Raises:
            DependencyError: If git operation fails.
        """
        if self.offline:
            # Try to use cached version
            cached_path = self.git_fetcher.get_cached_path(name)
            if cached_path:
                sha = self.git_fetcher.get_current_sha(cached_path)
                logger.info(f"📦 {name}: Using cached version ({sha[:8]})")
                return ResolvedDependency(
                    name=name,
                    path=cached_path,
                    source=DependencySource.GIT,
                    git_sha=sha,
                )
            raise DependencyError(name, "Not in cache (offline mode)")

        try:
            path = self.git_fetcher.fetch(name, spec)
            sha = self.git_fetcher.get_current_sha(path)
            logger.info(f"🌐 {name}: Fetched from git ({sha[:8]})")

            return ResolvedDependency(
                name=name,
                path=path,
                source=DependencySource.GIT,
                git_sha=sha,
            )
        except GitFetchError as e:
            raise DependencyError(name, f"Git fetch failed: {e.message}")

    def _resolve_from_lockfile(
        self,
        name: str,
        locked: LockedPackage,
        spec: DependencySpec,
    ) -> ResolvedDependency:
        """
        Resolve from lockfile (frozen mode).

        Args:
            name: Dependency name.
            locked: Locked package entry.
            spec: Original dependency specification.

        Returns:
            ResolvedDependency with pinned version.

        Raises:
            DependencyError: If frozen resolution fails.
        """
        if self.offline:
            cached_path = self.git_fetcher.get_cached_path(name)
            if cached_path:
                return ResolvedDependency(
                    name=name,
                    path=cached_path,
                    source=DependencySource.GIT_LOCKED,
                    git_sha=locked.rev,
                )
            raise DependencyError(name, "Not in cache (frozen + offline mode)")

        # Fetch specific SHA from lockfile
        try:
            # Create a spec with the locked SHA
            locked_spec = DependencySpec(
                git=locked.git or spec.git,
                rev=locked.rev,
            )
            path = self.git_fetcher.fetch(name, locked_spec)

            return ResolvedDependency(
                name=name,
                path=path,
                source=DependencySource.GIT_LOCKED,
                git_sha=locked.rev,
            )
        except GitFetchError as e:
            raise DependencyError(name, f"Failed to fetch locked version: {e.message}")


def resolve_dependencies(
    project_root: Path,
    frozen: bool = False,
    offline: bool = False,
) -> List[ResolvedDependency]:
    """
    Convenience function to resolve all dependencies.

    Args:
        project_root: Root directory containing jnkn.toml.
        frozen: Whether to enforce lockfile versions.
        offline: Whether to disable network calls.

    Returns:
        List of resolved dependencies.

    Raises:
        DependencyError: If resolution fails.
    """
    resolver = DependencyResolver(project_root, frozen=frozen, offline=offline)
    result = resolver.resolve()
    return result.dependencies


def update_lockfile(project_root: Path) -> Lockfile:
    """
    Update the lockfile with current resolved versions.

    Args:
        project_root: Root directory containing jnkn.toml.

    Returns:
        Updated Lockfile instance.
    """
    resolver = DependencyResolver(project_root, frozen=False)
    result = resolver.resolve()

    lockfile_path = project_root / "jnkn.lock"
    lockfile = Lockfile.load(lockfile_path)

    for update in result.lockfile_updates:
        lockfile.update_package(update)

    lockfile.save(lockfile_path)
    return lockfile
