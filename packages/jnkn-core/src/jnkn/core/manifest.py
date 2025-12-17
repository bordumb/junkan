"""
Manifest definition and parsing for jnkn.toml.

Defines the schema for multi-repository configuration, allowing users to
declare dependencies on other codebases (local paths or git repositories),
and explicit mappings between artifacts.

Phases:
    - Phase 1: Local path dependencies
    - Phase 2: Git remote dependencies with lockfile support
    - Phase 3: Explicit mappings for cross-domain connections
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class DependencySource(StrEnum):
    """
    Indicates the origin of a resolved dependency.

    Attributes:
        LOCAL: Explicit local path (e.g., path="../infra")
        LOCAL_OVERRIDE: Overridden via [tool.jnkn.sources]
        GIT: Remote git repository
        GIT_LOCKED: Pinned version from lockfile
    """

    LOCAL = "local"
    LOCAL_OVERRIDE = "override"
    GIT = "git"
    GIT_LOCKED = "git_locked"


@dataclass
class GitSpec:
    """
    Specification for a Git repository dependency.

    Attributes:
        git: The repository URL (HTTPS or SSH).
        branch: Target branch name (e.g., "main").
        tag: Target tag name (e.g., "v1.0.0").
        rev: Specific commit SHA for pinning.
    """

    git: str
    branch: Optional[str] = None
    tag: Optional[str] = None
    rev: Optional[str] = None

    def get_ref(self) -> str:
        """
        Get the most specific ref to checkout.

        Priority: rev > tag > branch > HEAD

        Returns:
            The git ref string to checkout.
        """
        return self.rev or self.tag or self.branch or "HEAD"


@dataclass
class DependencySpec:
    """
    A single dependency declaration from jnkn.toml.

    Can be a local path or a git reference. Supports both short-form
    and long-form TOML syntax.

    Attributes:
        path: Local filesystem path (relative to manifest).
        git: Git repository URL.
        branch: Git branch name.
        tag: Git tag name.
        rev: Git commit SHA.

    Examples:
        Short form: `infra = "../infrastructure"`
        Long form: `infra = { git = "https://...", branch = "main" }`
    """

    path: Optional[str] = None
    git: Optional[str] = None
    branch: Optional[str] = None
    tag: Optional[str] = None
    rev: Optional[str] = None

    def as_git_spec(self) -> Optional[GitSpec]:
        """
        Convert to GitSpec if this is a git dependency.

        Returns:
            GitSpec instance or None if this is a local path dependency.
        """
        if not self.git:
            return None
        return GitSpec(
            git=self.git,
            branch=self.branch,
            tag=self.tag,
            rev=self.rev,
        )

    @property
    def is_git(self) -> bool:
        """Check if this is a git dependency."""
        return self.git is not None

    @property
    def is_local(self) -> bool:
        """Check if this is a local path dependency."""
        return self.path is not None


@dataclass
class ResolvedDependency:
    """
    A dependency that has been successfully resolved to a local filesystem path.

    Attributes:
        name: The dependency name (key in jnkn.toml).
        path: Absolute path to the resolved directory.
        source: How the dependency was resolved.
        git_sha: Specific SHA if resolved from git.
    """

    name: str
    path: Path
    source: DependencySource
    git_sha: Optional[str] = None

    def __repr__(self) -> str:
        sha_part = f", sha={self.git_sha[:8]}" if self.git_sha else ""
        return f"ResolvedDependency({self.name!r}, {self.path}, {self.source.value}{sha_part})"


class MappingType(StrEnum):
    """
    Types of explicit mappings between artifacts.

    Attributes:
        PROVIDES: Source provides/satisfies target (directional).
        ALIAS: Source is an alias for target (bidirectional).
        IGNORE: Suppress orphan warning for target.
    """

    PROVIDES = "provides"
    ALIAS = "alias"
    IGNORE = "ignore"


@dataclass
class ExplicitMapping:
    """
    A user-defined mapping between nodes in the dependency graph.

    Explicit mappings override fuzzy matching with 100% confidence,
    allowing users to handle edge cases where automatic matching fails.

    Attributes:
        source: Source node ID or pattern (supports glob wildcards).
        target: Target node ID or pattern (supports glob wildcards).
        mapping_type: The type of mapping relationship.
        reason: Human-readable explanation for the mapping.

    Examples:
        Exact match: `"infra:output:db_endpoint" = "env:DATABASE_URL"`
        Pattern: `"infra:output:redis_*" = "env:REDIS_*"`
        Ignore: `"env:CI_BUILD_NUMBER" = { ignore = true, reason = "Set by GitHub" }`
    """

    source: str
    target: str
    mapping_type: MappingType = MappingType.PROVIDES
    reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for TOML output."""
        if self.mapping_type == MappingType.IGNORE:
            return {"ignore": True, "reason": self.reason}
        return self.target

    @classmethod
    def from_toml(cls, source: str, value: Union[str, Dict[str, Any]]) -> "ExplicitMapping":
        """
        Parse a mapping from TOML format.

        Args:
            source: The source node ID (key in [mappings] section).
            value: Either a string target or a dict with options.

        Returns:
            ExplicitMapping instance.
        """
        if isinstance(value, str):
            return cls(source=source, target=value)

        if isinstance(value, dict):
            if value.get("ignore"):
                return cls(
                    source=source,
                    target="",
                    mapping_type=MappingType.IGNORE,
                    reason=value.get("reason"),
                )
            if "alias" in value:
                return cls(
                    source=source,
                    target=value["alias"],
                    mapping_type=MappingType.ALIAS,
                    reason=value.get("reason"),
                )
            # Default provides
            return cls(
                source=source,
                target=value.get("target", ""),
                mapping_type=MappingType.PROVIDES,
                reason=value.get("reason"),
            )

        raise ValueError(f"Invalid mapping value for {source}: {value}")


@dataclass
class ToolJnknConfig:
    """
    Configuration from [tool.jnkn] section.

    Attributes:
        sources: Local path overrides for dependencies.
        min_confidence: Minimum confidence threshold for fuzzy matching.
        include: File patterns to include in scanning.
        exclude: File patterns to exclude from scanning.
    """

    sources: Dict[str, DependencySpec] = field(default_factory=dict)
    min_confidence: float = 0.5
    include: List[str] = field(default_factory=list)
    exclude: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ToolJnknConfig":
        """Parse from TOML dictionary."""
        sources = {}
        for name, spec in data.get("sources", {}).items():
            if isinstance(spec, dict):
                sources[name] = DependencySpec(**spec)

        return cls(
            sources=sources,
            min_confidence=data.get("min_confidence", 0.5),
            include=data.get("include", []),
            exclude=data.get("exclude", []),
        )


@dataclass
class ProjectManifest:
    """
    Represents the parsed content of a jnkn.toml file.

    This is the central configuration object for multi-repository support,
    containing dependencies, source overrides, and explicit mappings.

    Attributes:
        name: Project name.
        version: Project version string.
        description: Optional project description.
        dependencies: External dependencies keyed by name.
        source_overrides: Local path overrides for development.
        mappings: Explicit artifact mappings.
        tool_config: Additional [tool.jnkn] configuration.
    """

    name: str
    version: str = "0.0.0"
    description: str = ""
    dependencies: Dict[str, DependencySpec] = field(default_factory=dict)
    source_overrides: Dict[str, DependencySpec] = field(default_factory=dict)
    mappings: List[ExplicitMapping] = field(default_factory=list)
    tool_config: ToolJnknConfig = field(default_factory=ToolJnknConfig)

    @classmethod
    def load(cls, path: Path) -> "ProjectManifest":
        """
        Load and parse a jnkn.toml file.

        Args:
            path: Path to the jnkn.toml file.

        Returns:
            ProjectManifest: Parsed configuration object. Returns a default
            manifest if the file does not exist.

        Raises:
            ValueError: If the TOML file is malformed.
        """
        if not path.exists():
            return cls(name=path.parent.name)

        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
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

        # Parse [tool.jnkn] section
        tool_section = data.get("tool", {}).get("jnkn", {})
        tool_config = ToolJnknConfig.from_dict(tool_section)

        # Parse [mappings] section (Phase 3)
        mappings = []
        for source, value in data.get("mappings", {}).items():
            try:
                mapping = ExplicitMapping.from_toml(source, value)
                mappings.append(mapping)
            except ValueError as e:
                raise ValueError(f"Invalid mapping in {path}: {e}")

        return cls(
            name=project.get("name", path.parent.name),
            version=project.get("version", "0.0.0"),
            description=project.get("description", ""),
            dependencies=deps,
            source_overrides=tool_config.sources,
            mappings=mappings,
            tool_config=tool_config,
        )

    @classmethod
    def empty(cls, name: str = "unnamed") -> "ProjectManifest":
        """
        Create an empty manifest configuration.

        Args:
            name: Project name to use.

        Returns:
            Empty ProjectManifest instance.
        """
        return cls(name=name)

    def has_dependencies(self) -> bool:
        """Check if any dependencies are declared."""
        return len(self.dependencies) > 0

    def has_mappings(self) -> bool:
        """Check if any explicit mappings are declared."""
        return len(self.mappings) > 0

    def get_mapping_for_target(self, target_id: str) -> Optional[ExplicitMapping]:
        """
        Find an explicit mapping that targets the given node ID.

        Args:
            target_id: The target node ID to look for.

        Returns:
            ExplicitMapping if found, None otherwise.
        """
        for mapping in self.mappings:
            if mapping.target == target_id:
                return mapping
        return None

    def get_ignored_sources(self) -> List[str]:
        """
        Get list of source node IDs that should be ignored.

        Returns:
            List of source IDs with IGNORE mapping type.
        """
        return [m.source for m in self.mappings if m.mapping_type == MappingType.IGNORE]

    def to_toml_string(self) -> str:
        """
        Serialize the manifest back to TOML format.

        Returns:
            TOML-formatted string.
        """
        lines = []

        # [project] section
        lines.append("[project]")
        lines.append(f'name = "{self.name}"')
        lines.append(f'version = "{self.version}"')
        if self.description:
            lines.append(f'description = "{self.description}"')
        lines.append("")

        # [dependencies] section
        if self.dependencies:
            lines.append("[dependencies]")
            for name, spec in self.dependencies.items():
                if spec.path:
                    lines.append(f'{name} = "{spec.path}"')
                elif spec.git:
                    parts = [f'git = "{spec.git}"']
                    if spec.branch:
                        parts.append(f'branch = "{spec.branch}"')
                    if spec.tag:
                        parts.append(f'tag = "{spec.tag}"')
                    if spec.rev:
                        parts.append(f'rev = "{spec.rev}"')
                    lines.append(f"{name} = {{ {', '.join(parts)} }}")
            lines.append("")

        # [tool.jnkn.sources] section
        if self.source_overrides:
            lines.append("[tool.jnkn.sources]")
            for name, spec in self.source_overrides.items():
                if spec.path:
                    lines.append(f'{name} = {{ path = "{spec.path}" }}')
            lines.append("")

        # [mappings] section
        if self.mappings:
            lines.append("[mappings]")
            for mapping in self.mappings:
                if mapping.mapping_type == MappingType.IGNORE:
                    reason_part = f', reason = "{mapping.reason}"' if mapping.reason else ""
                    lines.append(f'"{mapping.source}" = {{ ignore = true{reason_part} }}')
                else:
                    lines.append(f'"{mapping.source}" = "{mapping.target}"')
            lines.append("")

        return "\n".join(lines)
