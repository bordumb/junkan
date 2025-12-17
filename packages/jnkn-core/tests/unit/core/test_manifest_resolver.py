"""
Unit tests for Manifest parsing and Dependency Resolution.
"""

import pytest
from pathlib import Path
from jnkn.core.manifest import ProjectManifest, DependencySource
from jnkn.core.resolver import DependencyResolver

# --- Manifest Tests ---

def test_manifest_load_defaults(tmp_path):
    """Test loading a non-existent manifest returns defaults."""
    manifest_path = tmp_path / "jnkn.toml"
    # Ensure file doesn't exist
    if manifest_path.exists():
        manifest_path.unlink()
        
    manifest = ProjectManifest.load(manifest_path)
    
    assert manifest.name == tmp_path.name
    assert manifest.version == "0.0.0"
    assert manifest.dependencies == {}

def test_manifest_load_valid(tmp_path):
    """Test loading a valid jnkn.toml with dependencies."""
    manifest_path = tmp_path / "jnkn.toml"
    manifest_content = """
    [project]
    name = "test-project"
    version = "1.2.3"

    [dependencies]
    infra = { path = "../infra" }
    shared = { git = "https://github.com/org/shared.git", branch = "main" }
    legacy = "../legacy"  # Short form

    [tool.jnkn.sources]
    shared = { path = "../local-shared" }
    """
    manifest_path.write_text(manifest_content)

    manifest = ProjectManifest.load(manifest_path)

    assert manifest.name == "test-project"
    assert manifest.version == "1.2.3"
    
    # Check dependencies
    assert manifest.dependencies["infra"].path == "../infra"
    assert manifest.dependencies["shared"].git == "https://github.com/org/shared.git"
    assert manifest.dependencies["shared"].branch == "main"
    assert manifest.dependencies["legacy"].path == "../legacy"

    # Check overrides
    assert manifest.source_overrides["shared"].path == "../local-shared"

def test_manifest_parsing_error(tmp_path):
    """Test proper error handling for invalid TOML."""
    manifest_path = tmp_path / "jnkn.toml"
    manifest_path.write_text("invalid [ toml")

    with pytest.raises(ValueError, match="Failed to parse"):
        ProjectManifest.load(manifest_path)

# --- Resolver Tests ---

def test_resolve_local_path(tmp_path):
    """Test resolving a valid local path dependency."""
    # Setup: Project and Infra directories
    project_dir = tmp_path / "app"
    project_dir.mkdir()
    
    infra_dir = tmp_path / "infra"
    infra_dir.mkdir()
    
    (project_dir / "jnkn.toml").write_text(f"""
    [dependencies]
    infra = {{ path = "../infra" }}
    """)

    resolver = DependencyResolver(project_dir)
    result = resolver.resolve()

    assert len(result.dependencies) == 1
    dep = result.dependencies[0]
    
    assert dep.name == "infra"
    assert dep.path.resolve() == infra_dir.resolve()
    assert dep.source == DependencySource.LOCAL

def test_resolve_missing_path(tmp_path):
    """Test error when local path doesn't exist."""
    project_dir = tmp_path / "app"
    project_dir.mkdir()
    
    (project_dir / "jnkn.toml").write_text("""
    [dependencies]
    missing = { path = "../does_not_exist" }
    """)

    resolver = DependencyResolver(project_dir)
    
    with pytest.raises(FileNotFoundError, match="Dependency 'missing' not found"):
        resolver.resolve()

def test_resolve_override_precedence(tmp_path):
    """Test that local overrides take precedence over git/other definitions."""
    project_dir = tmp_path / "app"
    project_dir.mkdir()
    
    # The "real" git source (simulated)
    # The local override path
    local_override = tmp_path / "shared-local"
    local_override.mkdir()

    (project_dir / "jnkn.toml").write_text(f"""
    [dependencies]
    # This would normally be a git dep, or a different path
    shared = {{ git = "https://example.com/repo.git" }}

    [tool.jnkn.sources]
    # Override with local path
    shared = {{ path = "../shared-local" }}
    """)

    resolver = DependencyResolver(project_dir)
    result = resolver.resolve()

    assert len(result.dependencies) == 1
    dep = result.dependencies[0]
    
    assert dep.name == "shared"
    assert dep.path.resolve() == local_override.resolve()
    assert dep.source == DependencySource.LOCAL_OVERRIDE

def test_resolve_git_raises_not_implemented(tmp_path):
    """Test that git dependencies raise NotImplementedError in Phase 1."""
    project_dir = tmp_path / "app"
    project_dir.mkdir()
    
    (project_dir / "jnkn.toml").write_text("""
    [dependencies]
    remote = { git = "https://github.com/org/repo.git" }
    """)

    resolver = DependencyResolver(project_dir)
    
    with pytest.raises(NotImplementedError, match="Git support is coming in Phase 2"):
        resolver.resolve()