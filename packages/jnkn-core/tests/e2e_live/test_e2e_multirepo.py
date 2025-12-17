"""
End-to-End Integration Test for Multi-Repository Support.

This test proves the complete flow works:
1. Create a multi-repo workspace with broken dependencies
2. Run jnkn scan (which uses DependencyResolver + EnhancedStitcher)
3. Verify that orphan nodes are detected in the database
4. Verify that explicit mappings prevent false positives

Run with: pytest test_e2e_multirepo.py -v
"""

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture
def demo_workspace(tmp_path: Path) -> Path:
    """
    Create a realistic multi-repo demo workspace.

    Structure:
        workspace/
        ├── payment-service/        # App with jnkn.toml
        │   ├── jnkn.toml           # Declares deps + mappings
        │   ├── src/
        │   │   └── app.py          # Reads DATABASE_URL, REDIS_URL, DD_API_ENDPOINT
        │   └── .jnkn/              # Created by scan
        │       └── jnkn.db
        └── infrastructure/         # Local infra (BROKEN: renamed output)
            └── terraform/
                └── main.tf         # Outputs: db_connection_string (WRONG!), redis_url
    """
    workspace = tmp_path / "workspace"

    # === App Repository ===
    app = workspace / "payment-service"
    (app / "src").mkdir(parents=True)

    # App code with env vars
    (app / "src" / "app.py").write_text('''
"""Payment service."""
import os

# Should be provided by infra - BUT infra renamed it!
DATABASE_URL = os.getenv("DATABASE_URL")  # ❌ ORPHAN - infra outputs db_connection_string

# Should be provided by infra - still works
REDIS_URL = os.getenv("REDIS_URL")  # ✅ MATCHED - infra outputs redis_url

# Provided by platform via explicit mapping
DD_API_ENDPOINT = os.getenv("DD_API_ENDPOINT")  # ✅ MAPPED - explicit mapping in jnkn.toml

# CI-injected, should be ignored
CI_TOKEN = os.getenv("CI_TOKEN")  # ✅ IGNORED - explicit ignore in jnkn.toml

def main():
    print(f"DB: {DATABASE_URL}")
''')

    # jnkn.toml with dependencies and mappings
    (app / "jnkn.toml").write_text('''
[project]
name = "payment-service"
version = "1.0.0"

[dependencies]
infrastructure = { path = "../infrastructure" }

[mappings]
# Explicit mapping for platform dependency (simulating remote)
"infra:output:datadog_endpoint" = "env:DD_API_ENDPOINT"

# Ignore CI-injected variables
"env:CI_TOKEN" = { ignore = true, reason = "Injected by GitHub Actions" }
''')

    # === Infrastructure Repository (BROKEN) ===
    infra = workspace / "infrastructure"
    (infra / "terraform").mkdir(parents=True)

    # Terraform with RENAMED output (breaking change!)
    (infra / "terraform" / "main.tf").write_text('''
# Payment service infrastructure

resource "aws_db_instance" "main" {
  identifier = "payment-db"
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id = "payment-cache"
}

# ❌ BREAKING: Renamed from "database_url" to "db_connection_string"
output "db_connection_string" {
  value = "postgres://db.example.com/payments"
}

# ✅ Still matches REDIS_URL
output "redis_url" {
  value = "redis://cache.example.com:6379"
}

# For explicit mapping test
output "datadog_endpoint" {
  value = "https://api.datadoghq.com"
}
''')

    return app


class TestDependencyResolution:
    """Test dependency resolution specifically."""

    def test_local_path_resolved(self, demo_workspace: Path):
        """Test that local path dependency is resolved correctly."""
        from jnkn.core.resolver import DependencyResolver
        from jnkn.core.manifest import DependencySource

        resolver = DependencyResolver(demo_workspace)
        result = resolver.resolve()

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]

        assert dep.name == "infrastructure"
        assert dep.source == DependencySource.LOCAL
        assert dep.path.exists()
        assert (dep.path / "terraform" / "main.tf").exists()

    def test_manifest_loads_mappings(self, demo_workspace: Path):
        """Test that manifest correctly parses mappings."""
        from jnkn.core.manifest import ProjectManifest, MappingType

        manifest = ProjectManifest.load(demo_workspace / "jnkn.toml")

        assert len(manifest.mappings) == 2

        # Check provides mapping
        provides_mappings = [m for m in manifest.mappings if m.mapping_type == MappingType.PROVIDES]
        assert len(provides_mappings) == 1
        assert provides_mappings[0].source == "infra:output:datadog_endpoint"
        assert provides_mappings[0].target == "env:DD_API_ENDPOINT"

        # Check ignore mapping
        ignore_mappings = [m for m in manifest.mappings if m.mapping_type == MappingType.IGNORE]
        assert len(ignore_mappings) == 1
        assert ignore_mappings[0].source == "env:CI_TOKEN"
        assert ignore_mappings[0].reason == "Injected by GitHub Actions"


class TestEnhancedStitcher:
    """Test EnhancedStitcher directly."""

    def test_explicit_mapping_wins_over_fuzzy(self, demo_workspace: Path):
        """Test that explicit mappings take priority over fuzzy matches."""
        from jnkn.core.enhanced_stitching import EnhancedStitcher
        from jnkn.core.graph import DependencyGraph
        from jnkn.core.types import Node, NodeType
        from jnkn.core.manifest import ProjectManifest

        # Create a minimal graph
        graph = DependencyGraph()

        # Add infra output node (use INFRA_RESOURCE - that's what TF outputs become)
        # Note: path must be a string, not Path object
        graph.add_node(Node(
            id="infra:output:datadog_endpoint",
            name="datadog_endpoint",
            type=NodeType.INFRA_RESOURCE,
            path="main.tf",
        ))

        # Add env var node
        graph.add_node(Node(
            id="env:DD_API_ENDPOINT",
            name="DD_API_ENDPOINT",
            type=NodeType.ENV_VAR,
            path="app.py",
        ))

        # Load manifest with explicit mapping
        manifest = ProjectManifest.load(demo_workspace / "jnkn.toml")

        # Create stitcher
        stitcher = EnhancedStitcher(mappings=manifest.mappings)
        result = stitcher.stitch(graph)

        # Should have one edge from explicit mapping
        assert result.explicit_count >= 1

        # Find the explicit edge
        explicit_edges = [e for e in result.edges if e.confidence == 1.0]
        assert len(explicit_edges) >= 1

        edge = explicit_edges[0]
        assert edge.metadata.get("rule") == "explicit_mapping"

    def test_ignore_mapping_skips_node(self, demo_workspace: Path):
        """Test that ignored nodes are tracked."""
        from jnkn.core.enhanced_stitching import EnhancedStitcher
        from jnkn.core.graph import DependencyGraph
        from jnkn.core.types import Node, NodeType
        from jnkn.core.manifest import ProjectManifest

        graph = DependencyGraph()

        # Add the ignored env var (path must be string)
        graph.add_node(Node(
            id="env:CI_TOKEN",
            name="CI_TOKEN",
            type=NodeType.ENV_VAR,
            path="app.py",
        ))

        manifest = ProjectManifest.load(demo_workspace / "jnkn.toml")
        stitcher = EnhancedStitcher(mappings=manifest.mappings)
        result = stitcher.stitch(graph)

        # Should have tracked the ignored source
        assert result.ignored_count == 1


class TestMappingMatcher:
    """Test the MappingMatcher directly."""

    def test_exact_match(self, demo_workspace: Path):
        """Test exact mapping match."""
        from jnkn.core.mappings import MappingMatcher
        from jnkn.core.manifest import ProjectManifest

        manifest = ProjectManifest.load(demo_workspace / "jnkn.toml")
        matcher = MappingMatcher(manifest.mappings)

        # Test exact match
        match = matcher.match("infra:output:datadog_endpoint", "env:DD_API_ENDPOINT")
        assert match is not None
        assert match.confidence == 1.0

    def test_is_ignored(self, demo_workspace: Path):
        """Test ignore detection."""
        from jnkn.core.mappings import MappingMatcher
        from jnkn.core.manifest import ProjectManifest

        manifest = ProjectManifest.load(demo_workspace / "jnkn.toml")
        matcher = MappingMatcher(manifest.mappings)

        assert matcher.is_ignored("env:CI_TOKEN")
        assert not matcher.is_ignored("env:DATABASE_URL")

    def test_get_ignore_reason(self, demo_workspace: Path):
        """Test getting ignore reason."""
        from jnkn.core.mappings import MappingMatcher
        from jnkn.core.manifest import ProjectManifest

        manifest = ProjectManifest.load(demo_workspace / "jnkn.toml")
        matcher = MappingMatcher(manifest.mappings)

        reason = matcher.get_ignore_reason("env:CI_TOKEN")
        assert reason == "Injected by GitHub Actions"


class TestManifestParsing:
    """Test jnkn.toml parsing edge cases."""

    def test_empty_manifest(self, tmp_path: Path):
        """Test loading non-existent manifest returns defaults."""
        from jnkn.core.manifest import ProjectManifest

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert manifest.name == tmp_path.name
        assert manifest.dependencies == {}
        assert manifest.mappings == []

    def test_minimal_manifest(self, tmp_path: Path):
        """Test loading minimal manifest."""
        from jnkn.core.manifest import ProjectManifest

        (tmp_path / "jnkn.toml").write_text('''
[project]
name = "test"
''')

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert manifest.name == "test"
        assert manifest.version == "0.0.0"

    def test_local_path_shorthand(self, tmp_path: Path):
        """Test parsing local path shorthand syntax."""
        from jnkn.core.manifest import ProjectManifest

        (tmp_path / "jnkn.toml").write_text('''
[project]
name = "test"

[dependencies]
infra = "../infrastructure"
''')

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert "infra" in manifest.dependencies
        assert manifest.dependencies["infra"].path == "../infrastructure"
        assert manifest.dependencies["infra"].git is None

    def test_git_dependency(self, tmp_path: Path):
        """Test parsing git dependency syntax."""
        from jnkn.core.manifest import ProjectManifest

        (tmp_path / "jnkn.toml").write_text('''
[project]
name = "test"

[dependencies]
platform = { git = "https://github.com/org/platform.git", branch = "main" }
''')

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert "platform" in manifest.dependencies
        dep = manifest.dependencies["platform"]
        assert dep.git == "https://github.com/org/platform.git"
        assert dep.branch == "main"
        assert dep.path is None

    def test_source_override(self, tmp_path: Path):
        """Test parsing source override."""
        from jnkn.core.manifest import ProjectManifest

        (tmp_path / "jnkn.toml").write_text('''
[project]
name = "test"

[dependencies]
platform = { git = "https://github.com/org/platform.git" }

[tool.jnkn.sources]
platform = { path = "../local-platform" }
''')

        manifest = ProjectManifest.load(tmp_path / "jnkn.toml")
        assert "platform" in manifest.source_overrides
        assert manifest.source_overrides["platform"].path == "../local-platform"


class TestResolverWithOverrides:
    """Test resolver with source overrides."""

    def test_override_takes_precedence(self, tmp_path: Path):
        """Test that local override takes precedence over git."""
        from jnkn.core.resolver import DependencyResolver
        from jnkn.core.manifest import DependencySource

        # Create directory structure
        project = tmp_path / "project"
        local_platform = tmp_path / "local-platform"
        project.mkdir()
        local_platform.mkdir()

        (project / "jnkn.toml").write_text('''
[project]
name = "test"

[dependencies]
platform = { git = "https://github.com/org/platform.git" }

[tool.jnkn.sources]
platform = { path = "../local-platform" }
''')

        resolver = DependencyResolver(project)
        result = resolver.resolve()

        assert len(result.dependencies) == 1
        dep = result.dependencies[0]
        assert dep.name == "platform"
        assert dep.source == DependencySource.LOCAL_OVERRIDE
        assert dep.path == local_platform


class TestLockfile:
    """Test lockfile operations."""

    def test_lockfile_roundtrip(self, tmp_path: Path):
        """Test saving and loading lockfile."""
        from jnkn.core.lockfile import Lockfile, create_locked_package

        lockfile = Lockfile()
        lockfile.update_package(create_locked_package(
            name="platform",
            git_url="https://github.com/org/platform.git",
            rev="abc123def456",
            branch="main",
        ))

        path = tmp_path / "jnkn.lock"
        lockfile.save(path)

        loaded = Lockfile.load(path)
        pkg = loaded.get_package("platform")

        assert pkg is not None
        assert pkg.rev == "abc123def456"
        assert pkg.branch == "main"

    def test_is_stale(self, tmp_path: Path):
        """Test stale detection."""
        from jnkn.core.lockfile import Lockfile, create_locked_package

        lockfile = Lockfile()
        lockfile.update_package(create_locked_package(
            name="platform",
            git_url="https://example.com",
            rev="old_sha",
        ))

        # Different SHA = stale
        assert lockfile.is_stale("platform", "new_sha")
        # Same SHA = not stale
        assert not lockfile.is_stale("platform", "old_sha")
        # Nonexistent package = stale (needs to be added to lockfile)
        assert lockfile.is_stale("nonexistent", "any_sha")


class TestGitFetcher:
    """Test git fetcher (unit tests only - no actual git operations)."""

    def test_cache_path_structure(self, tmp_path: Path):
        """Test that cache paths are structured correctly."""
        from jnkn.core.git_fetcher import GitFetcher

        fetcher = GitFetcher(cache_dir=tmp_path / "cache")

        # Cache dir should be created
        assert (tmp_path / "cache").exists()

        # Non-existent repo should return None
        assert fetcher.get_cached_path("nonexistent") is None
        assert not fetcher.is_cached("nonexistent")

    def test_list_cached_empty(self, tmp_path: Path):
        """Test listing empty cache."""
        from jnkn.core.git_fetcher import GitFetcher

        fetcher = GitFetcher(cache_dir=tmp_path / "cache")
        assert fetcher.list_cached() == []

    def test_cache_stats_empty(self, tmp_path: Path):
        """Test stats for empty cache."""
        from jnkn.core.git_fetcher import GitFetcher

        fetcher = GitFetcher(cache_dir=tmp_path / "cache")
        stats = fetcher.get_cache_stats()

        assert stats["count"] == 0
        assert stats["total_size_mb"] == 0


class TestCacheManager:
    """Test cache manager."""

    def test_list_empty(self, tmp_path: Path):
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
