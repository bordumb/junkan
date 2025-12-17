"""
Tests for Multi-Repository Support (Phase 1-3).

This module contains comprehensive tests for all multi-repo features:
- Phase 1: Local path dependencies
- Phase 2: Git remote dependencies & lockfile
- Phase 3: Explicit mappings
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestManifest:
    """Tests for jnkn.toml manifest parsing."""

    def test_load_empty_manifest(self, tmp_path: Path):
        """Test loading when no manifest exists."""
        from jnkn.core.manifest import ProjectManifest

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert manifest.name == tmp_path.name
        assert manifest.dependencies == {}

    def test_load_manifest_with_local_deps(self, tmp_path: Path):
        """Test parsing local path dependencies."""
        from jnkn.core.manifest import ProjectManifest

        manifest_content = """
[project]
name = "my-app"
version = "1.0.0"

[dependencies]
infra = "../infrastructure"
common = { path = "../common-libs" }
"""
        (tmp_path / "jnkn.toml").write_text(manifest_content)

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert manifest.name == "my-app"
        assert manifest.version == "1.0.0"
        assert "infra" in manifest.dependencies
        assert manifest.dependencies["infra"].path == "../infrastructure"
        assert "common" in manifest.dependencies
        assert manifest.dependencies["common"].path == "../common-libs"

    def test_load_manifest_with_git_deps(self, tmp_path: Path):
        """Test parsing git dependencies."""
        from jnkn.core.manifest import ProjectManifest

        manifest_content = """
[project]
name = "my-app"

[dependencies]
infra = { git = "https://github.com/org/infra.git", branch = "main" }
platform = { git = "https://github.com/org/platform.git", tag = "v1.0.0" }
pinned = { git = "https://github.com/org/pinned.git", rev = "abc123" }
"""
        (tmp_path / "jnkn.toml").write_text(manifest_content)

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert manifest.dependencies["infra"].git == "https://github.com/org/infra.git"
        assert manifest.dependencies["infra"].branch == "main"
        assert manifest.dependencies["platform"].tag == "v1.0.0"
        assert manifest.dependencies["pinned"].rev == "abc123"

    def test_load_manifest_with_overrides(self, tmp_path: Path):
        """Test parsing local source overrides."""
        from jnkn.core.manifest import ProjectManifest

        manifest_content = """
[project]
name = "my-app"

[dependencies]
infra = { git = "https://github.com/org/infra.git" }

[tool.jnkn.sources]
infra = { path = "../local-infra" }
"""
        (tmp_path / "jnkn.toml").write_text(manifest_content)

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert "infra" in manifest.source_overrides
        assert manifest.source_overrides["infra"].path == "../local-infra"

    def test_load_manifest_with_mappings(self, tmp_path: Path):
        """Test parsing explicit mappings (Phase 3)."""
        from jnkn.core.manifest import MappingType, ProjectManifest

        manifest_content = '''
[project]
name = "my-app"

[mappings]
"infra:output:db_endpoint" = "env:DATABASE_URL"
"env:CI_TOKEN" = { ignore = true, reason = "Set by GitHub Actions" }
'''
        (tmp_path / "jnkn.toml").write_text(manifest_content)

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert len(manifest.mappings) == 2

        # Check provides mapping
        db_mapping = next(m for m in manifest.mappings if m.source == "infra:output:db_endpoint")
        assert db_mapping.target == "env:DATABASE_URL"

        # Check ignore mapping
        ci_mapping = next(m for m in manifest.mappings if m.source == "env:CI_TOKEN")
        assert ci_mapping.mapping_type == MappingType.IGNORE
        assert ci_mapping.reason == "Set by GitHub Actions"


class TestResolver:
    """Tests for dependency resolution."""

    def test_resolve_local_path(self, tmp_path: Path):
        """Test resolving local path dependencies."""
        from jnkn.core.manifest import DependencySource
        from jnkn.core.resolver import DependencyResolver

        # Create project structure
        project = tmp_path / "app"
        infra = tmp_path / "infra"
        project.mkdir()
        infra.mkdir()

        manifest_content = """
[project]
name = "app"

[dependencies]
infra = "../infra"
"""
        (project / "jnkn.toml").write_text(manifest_content)

        resolver = DependencyResolver(project)
        result = resolver.resolve()

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep.name == "infra"
        assert dep.path == infra
        assert dep.source == DependencySource.LOCAL

    def test_resolve_with_override(self, tmp_path: Path):
        """Test that local overrides take precedence."""
        from jnkn.core.manifest import DependencySource
        from jnkn.core.resolver import DependencyResolver

        project = tmp_path / "app"
        local_infra = tmp_path / "local-infra"
        project.mkdir()
        local_infra.mkdir()

        manifest_content = """
[project]
name = "app"

[dependencies]
infra = { git = "https://github.com/org/infra.git" }

[tool.jnkn.sources]
infra = { path = "../local-infra" }
"""
        (project / "jnkn.toml").write_text(manifest_content)

        resolver = DependencyResolver(project)
        result = resolver.resolve()

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep.name == "infra"
        assert dep.source == DependencySource.LOCAL_OVERRIDE
        assert dep.path == local_infra

    def test_resolve_missing_path_raises(self, tmp_path: Path):
        """Test that missing paths raise an error."""
        from jnkn.core.resolver import DependencyError, DependencyResolver

        project = tmp_path / "app"
        project.mkdir()

        manifest_content = """
[project]
name = "app"

[dependencies]
missing = "../does-not-exist"
"""
        (project / "jnkn.toml").write_text(manifest_content)

        resolver = DependencyResolver(project)
        with pytest.raises(DependencyError) as exc:
            resolver.resolve()

        assert "missing" in str(exc.value)


class TestLockfile:
    """Tests for lockfile management."""

    def test_load_empty_lockfile(self, tmp_path: Path):
        """Test loading when lockfile doesn't exist."""
        from jnkn.core.lockfile import Lockfile

        lockfile = Lockfile.load(tmp_path / "jnkn.lock")
        assert len(lockfile) == 0

    def test_save_and_load_lockfile(self, tmp_path: Path):
        """Test roundtrip save/load."""
        from jnkn.core.lockfile import Lockfile, create_locked_package

        lockfile = Lockfile()
        lockfile.update_package(
            create_locked_package(
                name="infra",
                git_url="https://github.com/org/infra.git",
                rev="abc123def456",
                branch="main",
            )
        )

        lockfile_path = tmp_path / "jnkn.lock"
        lockfile.save(lockfile_path)

        # Reload
        loaded = Lockfile.load(lockfile_path)
        assert len(loaded) == 1
        pkg = loaded.get_package("infra")
        assert pkg is not None
        assert pkg.rev == "abc123def456"
        assert pkg.branch == "main"

    def test_is_stale(self, tmp_path: Path):
        """Test stale detection."""
        from jnkn.core.lockfile import Lockfile, create_locked_package

        lockfile = Lockfile()
        lockfile.update_package(
            create_locked_package(
                name="infra",
                git_url="https://example.com",
                rev="old_sha",
            )
        )

        assert lockfile.is_stale("infra", "new_sha")
        assert not lockfile.is_stale("infra", "old_sha")


class TestMappings:
    """Tests for explicit mappings (Phase 3)."""

    def test_exact_mapping_match(self):
        """Test exact mapping matching."""
        from jnkn.core.manifest import ExplicitMapping
        from jnkn.core.mappings import MappingMatcher

        mappings = [
            ExplicitMapping(
                source="infra:output:db_url",
                target="env:DATABASE_URL",
            )
        ]

        matcher = MappingMatcher(mappings)
        match = matcher.match("infra:output:db_url", "env:DATABASE_URL")

        assert match is not None
        assert match.confidence == 1.0

    def test_pattern_mapping_match(self):
        """Test wildcard pattern matching."""
        from jnkn.core.manifest import ExplicitMapping
        from jnkn.core.mappings import MappingMatcher

        mappings = [
            ExplicitMapping(
                source="infra:output:redis_*",
                target="env:REDIS_*",
            )
        ]

        matcher = MappingMatcher(mappings)

        # Should match
        match = matcher.match("infra:output:redis_url", "env:REDIS_URL")
        assert match is not None

        # Should not match (different wildcard value)
        match = matcher.match("infra:output:redis_url", "env:REDIS_HOST")
        assert match is None

    def test_ignore_mapping(self):
        """Test ignore mappings."""
        from jnkn.core.manifest import ExplicitMapping, MappingType
        from jnkn.core.mappings import MappingMatcher

        mappings = [
            ExplicitMapping(
                source="env:CI_TOKEN",
                target="",
                mapping_type=MappingType.IGNORE,
                reason="Set by CI",
            )
        ]

        matcher = MappingMatcher(mappings)
        assert matcher.is_ignored("env:CI_TOKEN")
        assert matcher.get_ignore_reason("env:CI_TOKEN") == "Set by CI"

    def test_expand_patterns(self):
        """Test pattern expansion against node IDs."""
        from jnkn.core.manifest import ExplicitMapping
        from jnkn.core.mappings import MappingMatcher

        mappings = [
            ExplicitMapping(
                source="infra:output:redis_*",
                target="env:REDIS_*",
            )
        ]

        matcher = MappingMatcher(mappings)
        node_ids = {
            "infra:output:redis_url",
            "infra:output:redis_port",
            "env:REDIS_URL",
            "env:REDIS_PORT",
            "env:REDIS_HOST",  # No matching source
        }

        matches = matcher.expand_patterns(node_ids)
        assert len(matches) == 2

        match_pairs = {(m.source_id, m.target_id) for m in matches}
        assert ("infra:output:redis_url", "env:REDIS_URL") in match_pairs
        assert ("infra:output:redis_port", "env:REDIS_PORT") in match_pairs


class TestMappingValidator:
    """Tests for mapping validation."""

    def test_validate_missing_source(self):
        """Test validation catches missing source nodes."""
        from jnkn.core.manifest import ExplicitMapping
        from jnkn.core.mappings import MappingValidator

        validator = MappingValidator(node_ids={"env:DATABASE_URL"})
        mappings = [
            ExplicitMapping(
                source="infra:output:missing",
                target="env:DATABASE_URL",
            )
        ]

        warnings = validator.validate(mappings)
        assert len(warnings) == 1
        assert "source" in warnings[0].message.lower()

    def test_validate_missing_target(self):
        """Test validation catches missing target nodes."""
        from jnkn.core.manifest import ExplicitMapping
        from jnkn.core.mappings import MappingValidator

        validator = MappingValidator(node_ids={"infra:output:db_url"})
        mappings = [
            ExplicitMapping(
                source="infra:output:db_url",
                target="env:MISSING_VAR",
            )
        ]

        warnings = validator.validate(mappings)
        assert len(warnings) == 1
        assert "target" in warnings[0].message.lower()

    def test_validate_conflicting_mappings(self):
        """Test validation catches conflicting mappings."""
        from jnkn.core.manifest import ExplicitMapping
        from jnkn.core.mappings import MappingValidator

        validator = MappingValidator(
            node_ids={
                "infra:output:db",
                "env:DB_URL",
                "env:DATABASE_URL",
            }
        )
        mappings = [
            ExplicitMapping(
                source="infra:output:db",
                target="env:DB_URL",
            ),
            ExplicitMapping(
                source="infra:output:db",
                target="env:DATABASE_URL",
            ),
        ]

        warnings = validator.validate(mappings)
        conflict_warnings = [w for w in warnings if w.code == "conflicting-mappings"]
        assert len(conflict_warnings) == 1


class TestCacheManager:
    """Tests for cache management."""

    def test_list_empty_cache(self, tmp_path: Path):
        """Test listing empty cache."""
        from jnkn.core.cache import CacheManager

        manager = CacheManager(cache_dir=tmp_path / "cache")
        items = manager.list()
        assert len(items) == 0

    def test_get_stats_empty(self, tmp_path: Path):
        """Test stats for empty cache."""
        from jnkn.core.cache import CacheManager

        manager = CacheManager(cache_dir=tmp_path / "cache")
        stats = manager.get_stats()
        assert stats.total_repos == 0
        assert stats.total_size_bytes == 0


class TestGitFetcher:
    """Tests for git fetcher."""

    def test_get_cached_path_not_exists(self, tmp_path: Path):
        """Test getting path for non-existent cache."""
        from jnkn.core.git_fetcher import GitFetcher

        fetcher = GitFetcher(cache_dir=tmp_path / "cache")
        path = fetcher.get_cached_path("nonexistent")
        assert path is None

    def test_is_cached_false(self, tmp_path: Path):
        """Test is_cached for non-existent."""
        from jnkn.core.git_fetcher import GitFetcher

        fetcher = GitFetcher(cache_dir=tmp_path / "cache")
        assert not fetcher.is_cached("nonexistent")


class TestIntegration:
    """Integration tests for the full multi-repo flow."""

    def test_full_local_dependency_flow(self, tmp_path: Path):
        """Test complete flow with local dependencies."""
        from jnkn.core.manifest import ProjectManifest
        from jnkn.core.resolver import DependencyResolver

        # Create project structure
        workspace = tmp_path / "workspace"
        app = workspace / "app"
        infra = workspace / "infra"

        app.mkdir(parents=True)
        infra.mkdir(parents=True)

        # Create app manifest
        (app / "jnkn.toml").write_text("""
[project]
name = "my-app"
version = "1.0.0"

[dependencies]
infra = "../infra"
""")

        # Create infra file
        (infra / "main.tf").write_text("""
output "database_url" {
  value = "postgres://..."
}
""")

        # Test resolution
        resolver = DependencyResolver(app)
        result = resolver.resolve()

        assert len(result.dependencies) == 1
        assert result.dependencies[0].name == "infra"
        assert result.dependencies[0].path == infra

    def test_manifest_roundtrip(self, tmp_path: Path):
        """Test manifest serialization roundtrip."""
        from jnkn.core.manifest import (
            DependencySpec,
            ExplicitMapping,
            MappingType,
            ProjectManifest,
        )

        # Create manifest programmatically
        manifest = ProjectManifest(
            name="test-project",
            version="2.0.0",
            dependencies={
                "infra": DependencySpec(git="https://github.com/org/infra.git", branch="main"),
                "common": DependencySpec(path="../common"),
            },
            mappings=[
                ExplicitMapping(
                    source="infra:output:db",
                    target="env:DATABASE_URL",
                ),
                ExplicitMapping(
                    source="env:CI_TOKEN",
                    target="",
                    mapping_type=MappingType.IGNORE,
                    reason="Set by CI",
                ),
            ],
        )

        # Serialize
        toml_str = manifest.to_toml_string()

        # Write and reload
        manifest_path = tmp_path / "jnkn.toml"
        manifest_path.write_text(toml_str)

        loaded = ProjectManifest.load(manifest_path)

        # Verify
        assert loaded.name == "test-project"
        assert loaded.version == "2.0.0"
        assert len(loaded.dependencies) == 2
        assert len(loaded.mappings) == 2


# Fixture for common test setup
@pytest.fixture
def sample_workspace(tmp_path: Path) -> Path:
    """Create a sample multi-repo workspace for testing."""
    workspace = tmp_path / "workspace"

    # Create app
    app = workspace / "app"
    app.mkdir(parents=True)
    (app / "jnkn.toml").write_text("""
[project]
name = "sample-app"
version = "1.0.0"

[dependencies]
infra = "../infrastructure"
shared = "../shared-libs"

[tool.jnkn.sources]
infra = { path = "../local-infra" }

[mappings]
"infra:output:db_endpoint" = "env:DATABASE_URL"
"env:CI_TOKEN" = { ignore = true, reason = "GitHub Actions" }
""")
    (app / "src").mkdir()
    (app / "src" / "main.py").write_text("""
import os
DATABASE_URL = os.getenv("DATABASE_URL")
API_KEY = os.environ.get("API_KEY")
""")

    # Create infrastructure
    infra = workspace / "infrastructure"
    infra.mkdir(parents=True)
    (infra / "main.tf").write_text("""
output "db_endpoint" {
  value = aws_db_instance.main.endpoint
}

output "api_gateway_url" {
  value = aws_api_gateway_rest_api.main.invoke_url
}
""")

    # Create local-infra override
    local_infra = workspace / "local-infra"
    local_infra.mkdir(parents=True)
    (local_infra / "main.tf").write_text("""
output "db_endpoint" {
  value = "localhost:5432"
}
""")

    # Create shared libs
    shared = workspace / "shared-libs"
    shared.mkdir(parents=True)
    (shared / "utils.py").write_text("""
def connect_db():
    pass
""")

    return workspace


def test_sample_workspace_structure(sample_workspace: Path):
    """Test that the sample workspace fixture is set up correctly."""
    assert (sample_workspace / "app" / "jnkn.toml").exists()
    assert (sample_workspace / "infrastructure" / "main.tf").exists()
    assert (sample_workspace / "local-infra" / "main.tf").exists()
    assert (sample_workspace / "shared-libs" / "utils.py").exists()


def test_resolve_sample_workspace(sample_workspace: Path):
    """Test resolving dependencies in sample workspace."""
    from jnkn.core.manifest import DependencySource
    from jnkn.core.resolver import DependencyResolver

    app = sample_workspace / "app"
    resolver = DependencyResolver(app)
    result = resolver.resolve()

    # Should have 2 dependencies
    assert len(result.dependencies) == 2

    # infra should use local override
    infra_dep = next(d for d in result.dependencies if d.name == "infra")
    assert infra_dep.source == DependencySource.LOCAL_OVERRIDE
    assert infra_dep.path == sample_workspace / "local-infra"

    # shared should use path dependency
    shared_dep = next(d for d in result.dependencies if d.name == "shared")
    assert shared_dep.source == DependencySource.LOCAL
    assert shared_dep.path == sample_workspace / "shared-libs"
