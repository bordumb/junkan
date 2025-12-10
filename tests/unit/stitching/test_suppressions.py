"""
Unit tests for the User Suppressions System.

Tests cover:
- Glob pattern matching
- YAML round-trip persistence
- Expiration handling
- Integration with edge creation
"""

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from jnkn.stitching.suppressions import (
    Suppression,
    SuppressionAwareStitcher,
    SuppressionStore,
    create_default_store,
)


class TestSuppression:
    """Test Suppression model."""

    def test_basic_creation(self):
        """Test creating a basic suppression."""
        suppression = Suppression(
            source_pattern="env:*_ID",
            target_pattern="infra:*",
            reason="ID is too generic",
        )

        assert suppression.source_pattern == "env:*_ID"
        assert suppression.target_pattern == "infra:*"
        assert suppression.reason == "ID is too generic"
        assert suppression.id is not None
        assert suppression.enabled is True

    def test_auto_generated_id(self):
        """Test ID is auto-generated."""
        s1 = Suppression(source_pattern="env:A", target_pattern="infra:B")
        s2 = Suppression(source_pattern="env:C", target_pattern="infra:D")

        assert s1.id is not None
        assert s2.id is not None
        assert s1.id != s2.id

    def test_exact_pattern_match(self):
        """Test exact pattern matching (no wildcards)."""
        suppression = Suppression(
            source_pattern="env:HOST",
            target_pattern="infra:main",
        )

        assert suppression.matches("env:HOST", "infra:main") is True
        assert suppression.matches("env:HOST", "infra:backup") is False
        assert suppression.matches("env:PORT", "infra:main") is False

    def test_wildcard_pattern_match(self):
        """Test wildcard pattern matching."""
        suppression = Suppression(
            source_pattern="env:*_HOST",
            target_pattern="infra:*",
        )

        assert suppression.matches("env:DB_HOST", "infra:main") is True
        assert suppression.matches("env:REDIS_HOST", "infra:cache") is True
        assert suppression.matches("env:DB_PORT", "infra:main") is False

    def test_question_mark_pattern(self):
        """Test single character wildcard."""
        suppression = Suppression(
            source_pattern="env:DB?",
            target_pattern="infra:*",
        )

        assert suppression.matches("env:DB1", "infra:main") is True
        assert suppression.matches("env:DB2", "infra:main") is True
        assert suppression.matches("env:DB", "infra:main") is False
        assert suppression.matches("env:DB12", "infra:main") is False

    def test_bracket_pattern(self):
        """Test character class pattern."""
        suppression = Suppression(
            source_pattern="env:DB[123]",
            target_pattern="infra:*",
        )

        assert suppression.matches("env:DB1", "infra:main") is True
        assert suppression.matches("env:DB2", "infra:main") is True
        assert suppression.matches("env:DB4", "infra:main") is False

    def test_expiration_not_expired(self):
        """Test suppression is not expired."""
        suppression = Suppression(
            source_pattern="env:*",
            target_pattern="infra:*",
            # Future date = Active
            expires_at=datetime.now(timezone.utc) + timedelta(days=1)
        )

        assert suppression.is_expired() is False
        assert suppression.is_active() is True

    def test_expiration_expired(self):
        """Test suppression is expired."""
        suppression = Suppression(
            source_pattern="env:*",
            target_pattern="infra:*",
            # Past date = Expired
            expires_at=datetime.now(timezone.utc) - timedelta(days=1)
        )

        assert suppression.is_expired() is True
        assert suppression.is_active() is False
        assert suppression.matches("env:HOST", "infra:main") is False

    def test_no_expiration(self):
        """Test suppression without expiration."""
        suppression = Suppression(
            source_pattern="env:*",
            target_pattern="infra:*",
            expires_at=None,
        )

        assert suppression.is_expired() is False
        assert suppression.is_active() is True

    def test_disabled_suppression(self):
        """Test disabled suppression doesn't match."""
        suppression = Suppression(
            source_pattern="env:*",
            target_pattern="infra:*",
            enabled=False,
        )

        assert suppression.is_active() is False
        assert suppression.matches("env:HOST", "infra:main") is False

    def test_to_dict(self):
        """Test dictionary conversion."""
        suppression = Suppression(
            source_pattern="env:HOST",
            target_pattern="infra:*",
            reason="Test reason",
            created_by="tester",
        )

        d = suppression.to_dict()

        assert d["source"] == "env:HOST"
        assert d["target"] == "infra:*"
        assert d["reason"] == "Test reason"
        assert d["created_by"] == "tester"
        assert "created_at" in d

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "source": "env:HOST",
            "target": "infra:*",
            "reason": "Test reason",
            "created_by": "tester",
            "created_at": "2024-01-15T10:00:00",
        }

        suppression = Suppression.from_dict(data)

        assert suppression.source_pattern == "env:HOST"
        assert suppression.target_pattern == "infra:*"
        assert suppression.reason == "Test reason"

    def test_roundtrip_dict(self):
        """Test dict -> Suppression -> dict roundtrip."""
        original = Suppression(
            source_pattern="env:*_HOST",
            target_pattern="infra:*_db",
            reason="Too generic",
            created_by="admin",
        )

        d = original.to_dict()
        restored = Suppression.from_dict(d)

        assert restored.source_pattern == original.source_pattern
        assert restored.target_pattern == original.target_pattern
        assert restored.reason == original.reason
        assert restored.created_by == original.created_by


class TestSuppressionStore:
    """Test SuppressionStore persistence and operations."""

    def test_empty_store(self):
        """Test empty store behavior."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            assert store.count == 0
            assert store.list() == []

    def test_add_suppression(self):
        """Test adding a suppression."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            suppression = store.add(
                source_pattern="env:HOST",
                target_pattern="infra:*",
                reason="Too generic",
            )

            assert store.count == 1
            assert suppression.source_pattern == "env:HOST"

    def test_remove_suppression_by_id(self):
        """Test removing by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            s = store.add(source_pattern="env:A", target_pattern="infra:B")
            assert store.count == 1

            result = store.remove(s.id)
            assert result is True
            assert store.count == 0

    def test_remove_suppression_by_index(self):
        """Test removing by index (1-based)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            store.add(source_pattern="env:A", target_pattern="infra:A")
            store.add(source_pattern="env:B", target_pattern="infra:B")
            assert store.count == 2

            result = store.remove_by_index(1)  # Remove first
            assert result is True
            assert store.count == 1
            assert store.list()[0].source_pattern == "env:B"

    def test_is_suppressed(self):
        """Test checking if edge is suppressed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            store.add(
                source_pattern="env:*_ID",
                target_pattern="infra:*",
                reason="ID fields are generic",
            )

            match = store.is_suppressed("env:USER_ID", "infra:main")
            assert match.suppressed is True
            assert "ID" in match.reason or "generic" in match.reason

            match = store.is_suppressed("env:DATABASE_HOST", "infra:main")
            assert match.suppressed is False

    def test_save_and_load(self):
        """Test YAML persistence."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"

            # Create and save
            store1 = SuppressionStore(path)
            store1.load()
            store1.add(
                source_pattern="env:HOST",
                target_pattern="infra:*",
                reason="Test reason",
                created_by="tester",
            )
            store1.save()

            # Load in new store
            store2 = SuppressionStore(path)
            store2.load()

            assert store2.count == 1
            s = store2.list()[0]
            assert s.source_pattern == "env:HOST"
            assert s.reason == "Test reason"

    def test_yaml_format(self):
        """Test YAML file format is readable."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"

            store = SuppressionStore(path)
            store.load()
            store.add(
                source_pattern="env:HOST",
                target_pattern="infra:*",
                reason="Too generic",
                created_by="admin",
            )
            store.save()

            # Read raw YAML
            with open(path) as f:
                data = yaml.safe_load(f)

            assert "suppressions" in data
            assert len(data["suppressions"]) == 1
            assert data["suppressions"][0]["source"] == "env:HOST"

    def test_clear_expired(self):
        """Test clearing expired suppressions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            # Add one expired
            store._suppressions.append(Suppression(
                source_pattern="env:A",
                target_pattern="infra:A",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1)
            ))
            
            # Add one active (future expiration)
            store._suppressions.append(Suppression(
                source_pattern="env:B",
                target_pattern="infra:B",
                expires_at=datetime.now(timezone.utc) + timedelta(days=1)
            ))

            assert store.count == 2
            removed = store.clear_expired()

            assert removed == 1
            assert store.count == 1
            assert store.list()[0].source_pattern == "env:B"

    def test_find_matching(self):
        """Test finding all matching suppressions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            store.add(source_pattern="env:*", target_pattern="infra:*")
            store.add(source_pattern="env:*_HOST", target_pattern="infra:*")
            store.add(source_pattern="env:SPECIFIC", target_pattern="infra:specific")

            matches = store.find_matching("env:DB_HOST", "infra:main")

            # Should match first two, not third
            assert len(matches) == 2

    def test_get_by_id(self):
        """Test getting suppression by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            s = store.add(source_pattern="env:HOST", target_pattern="infra:*")

            found = store.get_by_id(s.id)
            assert found is not None
            assert found.source_pattern == "env:HOST"

            not_found = store.get_by_id("nonexistent")
            assert not_found is None

    def test_active_count(self):
        """Test counting active suppressions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            # Active
            store.add(source_pattern="env:A", target_pattern="infra:A")

            # Expired
            store._suppressions.append(Suppression(
                source_pattern="env:B",
                target_pattern="infra:B",
                expires_at=datetime.now(timezone.utc) - timedelta(days=1)
            ))

            assert store.count == 2
            assert store.active_count == 1


class TestSuppressionAwareStitcher:
    """Test integration with edge creation."""

    def test_allows_non_suppressed(self):
        """Test non-suppressed edges are allowed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()

            stitcher = SuppressionAwareStitcher(store)

            assert stitcher.should_create_edge("env:DATABASE_URL", "infra:rds") is True

    def test_blocks_suppressed(self):
        """Test suppressed edges are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()
            store.add(source_pattern="env:*_ID", target_pattern="infra:*")

            stitcher = SuppressionAwareStitcher(store)

            assert stitcher.should_create_edge("env:USER_ID", "infra:main") is False

    def test_tracks_suppressed_count(self):
        """Test suppression statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()
            store.add(source_pattern="env:*_ID", target_pattern="infra:*")

            stitcher = SuppressionAwareStitcher(store)

            stitcher.should_create_edge("env:USER_ID", "infra:main")
            stitcher.should_create_edge("env:ORDER_ID", "infra:main")
            stitcher.should_create_edge("env:DATABASE_URL", "infra:main")

            assert stitcher.suppressed_count == 2
            assert len(stitcher.suppressed_edges) == 2

    def test_reset_stats(self):
        """Test resetting statistics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"
            store = SuppressionStore(path)
            store.load()
            store.add(source_pattern="env:*", target_pattern="infra:*")

            stitcher = SuppressionAwareStitcher(store)

            stitcher.should_create_edge("env:A", "infra:B")
            assert stitcher.suppressed_count == 1

            stitcher.reset_stats()
            assert stitcher.suppressed_count == 0
            assert stitcher.suppressed_edges == []


class TestCreateDefaultStore:
    """Test factory function."""

    def test_creates_store(self):
        """Test factory creates working store."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "test.yaml"
            store = create_default_store(path)

            assert store.count == 0
            store.add(source_pattern="env:A", target_pattern="infra:B")
            assert store.count == 1


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_file(self):
        """Test loading from non-existent file."""
        store = SuppressionStore(Path("/nonexistent/path/file.yaml"))
        count = store.load()

        assert count == 0
        assert store.count == 0

    def test_invalid_yaml(self):
        """Test handling invalid YAML."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "suppressions.yaml"

            # Write invalid YAML
            with open(path, "w") as f:
                f.write("invalid: yaml: content: [[[")

            store = SuppressionStore(path)
            count = store.load()

            # Should handle gracefully
            assert count == 0

    def test_empty_patterns(self):
        """Test handling empty patterns."""
        suppression = Suppression(
            source_pattern="",
            target_pattern="",
        )

        # Empty pattern matches empty string
        assert suppression.matches("", "") is True
        assert suppression.matches("env:HOST", "infra:main") is False

    def test_special_characters_in_pattern(self):
        """Test patterns with special characters."""
        suppression = Suppression(
            source_pattern="env:DB[_-]HOST",
            target_pattern="infra:*",
        )

        # Bracket is fnmatch character class
        assert suppression.matches("env:DB_HOST", "infra:main") is True
        assert suppression.matches("env:DB-HOST", "infra:main") is True
        assert suppression.matches("env:DBXHOST", "infra:main") is False