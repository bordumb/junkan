"""
Manifest definition and parsing for jnkn.toml.

Defines the schema for multi-repository configuration, allowing users to
declare dependencies on other codebases (local paths or git repositories).
"""

import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Dict, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:
    # Fallback for older python versions if needed
    import tomli as tomllib


class DependencySource(StrEnum):
    """
    Indicates the origin of a resolved dependency.
    """

    LOCAL = "local"  # Explicit local path (e.g. path="../infra")
    LOCAL_OVERRIDE = "override"  # Overridden via [tool.jnkn.sources]
    GIT = "git"  # Remote git repository
    GIT_LOCKED = "git_locked"  # Pinned version from lockfile


@dataclass
class GitSpec:
    """
    Specification for a Git repository dependency.
    """

    git: str
    branch: Optional[str] = None
    tag: Optional[str] = None
    rev: Optional[str] = None


@dataclass
class DependencySpec:
    """
    A single dependency declaration from jnkn.toml.

    Can be a local path or a git reference.
    """

    path: Optional[str] = None
    git: Optional[str] = None
    branch: Optional[str] = None
    tag: Optional[str] = None
    rev: Optional[str] = None

    def as_git_spec(self) -> Optional[GitSpec]:
        """Convert to GitSpec if this is a git dependency."""
        if not self.git:
            return None
        return GitSpec(
            git=self.git,
            branch=self.branch,
            tag=self.tag,
            rev=self.rev,
        )


@dataclass
class ResolvedDependency:
    """
    A dependency that has been successfully resolved to a local filesystem path.
    """

    name: str
    path: Path
    source: DependencySource
    git_sha: Optional[str] = None  # Specific SHA if from git


@dataclass
class ProjectManifest:
    """
    Represents the parsed content of a jnkn.toml file.
    """

    name: str
    version: str = "0.0.0"
    dependencies: Dict[str, DependencySpec] = field(default_factory=dict)
    source_overrides: Dict[str, DependencySpec] = field(default_factory=dict)
    mappings: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "ProjectManifest":
        """
        Load and parse a jnkn.toml file.

        Args:
            path: Path to the jnkn.toml file.

        Returns:
            ProjectManifest: Parsed configuration object. Returns a default
            manifest if the file does not exist.
        """
        if not path.exists():
            # Return valid default if no manifest exists (monorepo mode)
            return cls(name=path.parent.name)

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            # Wrap toml parsing errors
            raise ValueError(f"Failed to parse {path}: {e}")

        project = data.get("project", {})

        # Parse [dependencies]
        deps = {}
        for name, spec in data.get("dependencies", {}).items():
            if isinstance(spec, str):
                # Short form: infra = "../path"
                deps[name] = DependencySpec(path=spec)
            elif isinstance(spec, dict):
                # Long form: infra = { git = "...", branch = "main" }
                deps[name] = DependencySpec(**spec)

        # Parse [tool.jnkn.sources] overrides
        overrides = {}
        tool_section = data.get("tool", {}).get("jnkn", {})
        for name, spec in tool_section.get("sources", {}).items():
            if isinstance(spec, dict):
                overrides[name] = DependencySpec(**spec)

        return cls(
            name=project.get("name", path.parent.name),
            version=project.get("version", "0.0.0"),
            dependencies=deps,
            source_overrides=overrides,
            mappings=data.get("mappings", {}),
        )

    @classmethod
    def empty(cls, name: str = "unnamed") -> "ProjectManifest":
        """Create an empty manifest configuration."""
        return cls(name=name)
