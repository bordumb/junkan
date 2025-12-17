"""
Dependency Resolver.

Responsible for resolving abstract dependencies declared in jnkn.toml
into concrete local filesystem paths.

Phase 1 Support:
- Local path dependencies
- Local path overrides via [tool.jnkn.sources]
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .manifest import (
    DependencySource,
    DependencySpec,
    ProjectManifest,
    ResolvedDependency,
)

logger = logging.getLogger(__name__)


@dataclass
class ResolutionResult:
    """
    Result container for the resolution process.
    """

    dependencies: List[ResolvedDependency]
    warnings: List[str]
    lockfile_stale: bool = False


class DependencyResolver:
    """
    Resolves dependencies from manifest to concrete paths.

    Resolution Strategy (Phase 1):
    1. Check for local overrides in [tool.jnkn.sources].
    2. Check for local path dependencies in [dependencies].
    3. (Future) Git dependencies.
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
            frozen: (Future) Whether to enforce lockfile versions.
            offline: (Future) Whether to disable network calls.
        """
        self.project_root = project_root
        self.frozen = frozen
        self.offline = offline

    def resolve(self) -> ResolutionResult:
        """
        Resolve all dependencies declared in the manifest.

        Returns:
            ResolutionResult containing list of resolved paths and any warnings.
        """
        manifest_path = self.project_root / "jnkn.toml"
        manifest = ProjectManifest.load(manifest_path)

        resolved_deps = []
        warnings = []

        for name, spec in manifest.dependencies.items():
            try:
                dep = self._resolve_single(name, spec, manifest.source_overrides)
                resolved_deps.append(dep)
            except Exception as e:
                # Log error but raise to fail fast in CLI
                logger.error(f"Failed to resolve dependency '{name}': {e}")
                raise

        return ResolutionResult(
            dependencies=resolved_deps,
            warnings=warnings,
        )

    def _resolve_single(
        self,
        name: str,
        spec: DependencySpec,
        overrides: dict[str, DependencySpec],
    ) -> ResolvedDependency:
        """
        Resolve a single dependency name.
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

        # 2. Local path dependency
        if spec.path:
            local_path = (self.project_root / spec.path).resolve()
            if not local_path.exists():
                raise FileNotFoundError(f"Dependency '{name}' not found at {local_path}")

            logger.info(f"📁 {name}: Using local path {local_path}")
            return ResolvedDependency(
                name=name,
                path=local_path,
                source=DependencySource.LOCAL,
            )

        # 3. Git dependency (Phase 2 Placeholder)
        if spec.git:
            # For Phase 1, we just raise a helpful error if someone tries to use git
            raise NotImplementedError(
                f"Git dependency '{name}' found. Git support is coming in Phase 2. "
                "Please use a local path override for now."
            )

        raise ValueError(f"Dependency '{name}' has no valid source (path or git)")
