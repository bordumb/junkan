"""
Tests for Framework Pack loading and application.
"""

import pytest
from pathlib import Path
import tempfile

from jnkn.core.packs.loader import (
    FrameworkPack,
    BoostPattern,
    AutoSuppression,
    PackLoader,
    load_pack,
    detect_and_suggest_pack,
)


class TestFrameworkPack:
    """Tests for FrameworkPack."""
    
    @pytest.fixture
    def sample_pack(self):
        """Create a sample pack for testing."""
        return FrameworkPack(
            name="test-pack",
            version="1.0.0",
            description="Test pack",
            boost_patterns=[
                BoostPattern(
                    pattern="*_DATABASE_*",
                    boost=0.15,
                    reason="Database connections"
                ),
            ],
            auto_suppress=[
                AutoSuppression(
                    source="env:DEBUG",
                    target="infra:*",
                    reason="Debug is app config"
                ),
            ],
            token_weights={
                "django": 0.2,
                "rds": 0.9,
            },
            blocked_tokens=["app", "config"],
        )
    
    def test_get_boost_for_pattern_match(self, sample_pack):
        """Test boost calculation for matching pattern."""
        boost = sample_pack.get_boost_for_pattern(
            "MY_DATABASE_HOST",
            "some_target"
        )
        assert boost == 0.15
    
    def test_get_boost_for_pattern_no_match(self, sample_pack):
        """Test boost calculation for non-matching pattern."""
        boost = sample_pack.get_boost_for_pattern(
            "SOME_OTHER_VAR",
            "some_target"
        )
        assert boost == 0.0
    
    def test_should_auto_suppress_match(self, sample_pack):
        """Test auto-suppression matching."""
        should_suppress, reason = sample_pack.should_auto_suppress(
            "env:DEBUG",
            "infra:something"
        )
        assert should_suppress is True
        assert "app config" in reason
    
    def test_should_auto_suppress_no_match(self, sample_pack):
        """Test auto-suppression non-matching."""
        should_suppress, reason = sample_pack.should_auto_suppress(
            "env:DATABASE_URL",
            "infra:rds"
        )
        assert should_suppress is False
    
    def test_get_token_weight_exists(self, sample_pack):
        """Test getting existing token weight."""
        weight = sample_pack.get_token_weight("rds")
        assert weight == 0.9
    
    def test_get_token_weight_not_exists(self, sample_pack):
        """Test getting non-existing token weight."""
        weight = sample_pack.get_token_weight("unknown")
        assert weight is None
    
    def test_is_blocked_token(self, sample_pack):
        """Test blocked token check."""
        assert sample_pack.is_blocked_token("app") is True
        assert sample_pack.is_blocked_token("APP") is True  # Case insensitive
        assert sample_pack.is_blocked_token("database") is False


class TestPackLoader:
    """Tests for PackLoader."""
    
    def test_get_available_packs(self):
        """Test getting list of available packs."""
        loader = PackLoader()
        packs = loader.get_available_packs()
        
        # Should include built-in packs
        assert "django-aws" in packs
        assert "fastapi-aws" in packs
    
    def test_load_builtin_pack(self):
        """Test loading a built-in pack."""
        pack = load_pack("django-aws")
        
        assert pack is not None
        assert pack.name == "django-aws"
        assert len(pack.boost_patterns) > 0
        assert len(pack.auto_suppress) > 0
    
    def test_load_nonexistent_pack(self):
        """Test loading a pack that doesn't exist."""
        pack = load_pack("nonexistent-pack")
        assert pack is None


class TestPackDetection:
    """Tests for automatic pack detection."""
    
    def test_detect_django_project(self):
        """Test detecting a Django project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create Django indicators
            (root / "requirements.txt").write_text("django==4.0\n")
            (root / "terraform").mkdir()
            (root / "terraform" / "main.tf").write_text("")
            
            pack_name = detect_and_suggest_pack(root)
            assert pack_name == "django-aws"
    
    def test_detect_fastapi_project(self):
        """Test detecting a FastAPI project."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create FastAPI indicators
            (root / "requirements.txt").write_text("fastapi==0.100\n")
            (root / "infra").mkdir()
            (root / "infra" / "main.tf").write_text("")
            
            pack_name = detect_and_suggest_pack(root)
            assert pack_name == "fastapi-aws"
    
    def test_detect_no_match(self):
        """Test detection when no pack matches."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            
            # Create empty project
            (root / "README.md").write_text("# Empty project")
            
            pack_name = detect_and_suggest_pack(root)
            assert pack_name is None
