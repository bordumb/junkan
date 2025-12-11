"""
User Suppressions System for jnkn.

This module provides a system for users to suppress false positive matches.
Suppressions can be pattern-based (using glob patterns) and have optional
expiration dates.

Features:
- Glob pattern matching for flexible suppression
- YAML-based persistence
- Expiration support
- Integration with the Stitcher

Storage Location: .jnkn/suppressions.yaml
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class Suppression(BaseModel):
    """
    A single suppression rule.
    
    Matches source/target pairs using glob patterns.
    """
    source_pattern: str = Field(..., description="Glob pattern for source node (e.g., 'env:*_ID')")
    target_pattern: str = Field(..., description="Glob pattern for target node (e.g., 'infra:*')")
    reason: str = Field(default="", description="Why this suppression exists")
    created_by: str = Field(default="unknown", description="Who created this suppression")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="When created")
    expires_at: datetime | None = Field(default=None, description="Optional expiration")
    id: str | None = Field(default=None, description="Unique identifier")
    enabled: bool = Field(default=True, description="Whether suppression is active")

    def model_post_init(self, __context) -> None:
        """Generate ID if not provided."""
        if self.id is None:
            # Generate ID from pattern hash
            import hashlib
            content = f"{self.source_pattern}|{self.target_pattern}|{self.created_at.isoformat()}"
            object.__setattr__(self, 'id', hashlib.md5(content.encode()).hexdigest()[:8])

    def is_expired(self) -> bool:
        """Check if this suppression has expired."""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def is_active(self) -> bool:
        """Check if this suppression is currently active."""
        return self.enabled and not self.is_expired()

    def matches(self, source_id: str, target_id: str) -> bool:
        """
        Check if this suppression matches a source/target pair.
        
        Uses glob pattern matching (fnmatch).
        """
        if not self.is_active():
            return False

        source_matches = fnmatch(source_id, self.source_pattern)
        target_matches = fnmatch(target_id, self.target_pattern)

        return source_matches and target_matches

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for YAML serialization."""
        result = {
            "source": self.source_pattern,
            "target": self.target_pattern,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
        }
        if self.expires_at:
            result["expires_at"] = self.expires_at.isoformat()
        if self.id:
            result["id"] = self.id
        if not self.enabled:
            result["enabled"] = False
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Suppression":
        """Create from dictionary (YAML deserialization)."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)

        expires_at = data.get("expires_at")
        if isinstance(expires_at, str):
            expires_at = datetime.fromisoformat(expires_at)

        return cls(
            source_pattern=data.get("source", data.get("source_pattern", "*")),
            target_pattern=data.get("target", data.get("target_pattern", "*")),
            reason=data.get("reason", ""),
            created_by=data.get("created_by", "unknown"),
            created_at=created_at or datetime.utcnow(),
            expires_at=expires_at,
            id=data.get("id"),
            enabled=data.get("enabled", True),
        )

    class Config:
        frozen = False


@dataclass
class SuppressionMatch:
    """Result of checking if an edge is suppressed."""
    suppressed: bool
    suppression: Suppression | None = None
    reason: str = ""


class SuppressionStore:
    """
    Manages suppression rules with YAML persistence.
    
    Usage:
        store = SuppressionStore()
        store.load()
        
        # Add suppression
        store.add(Suppression(
            source_pattern="env:HOST",
            target_pattern="infra:*",
            reason="HOST is too generic"
        ))
        
        # Check if edge is suppressed
        if store.is_suppressed("env:HOST", "infra:main"):
            print("Suppressed!")
        
        # Save changes
        store.save()
    """

    DEFAULT_PATH = Path(".jnkn/suppressions.yaml")

    def __init__(self, path: Path | None = None):
        """
        Initialize the suppression store.
        
        Args:
            path: Path to YAML file. Defaults to .jnkn/suppressions.yaml
        """
        self.path = path or self.DEFAULT_PATH
        self._suppressions: List[Suppression] = []
        self._loaded = False

    def load(self) -> int:
        """
        Load suppressions from YAML file.
        
        Returns:
            Number of suppressions loaded
        """
        if not self.path.exists():
            logger.debug(f"Suppressions file not found: {self.path}")
            self._loaded = True
            return 0

        try:
            with open(self.path, "r") as f:
                data = yaml.safe_load(f)

            if not data:
                self._suppressions = []
                self._loaded = True
                return 0

            suppressions_data = data.get("suppressions", [])
            self._suppressions = [
                Suppression.from_dict(s) for s in suppressions_data
            ]

            self._loaded = True
            logger.info(f"Loaded {len(self._suppressions)} suppressions from {self.path}")
            return len(self._suppressions)

        except Exception as e:
            logger.error(f"Failed to load suppressions: {e}")
            self._suppressions = []
            self._loaded = True
            return 0

    def save(self) -> bool:
        """
        Save suppressions to YAML file.
        
        Returns:
            True if successful
        """
        try:
            # Ensure directory exists
            self.path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "suppressions": [s.to_dict() for s in self._suppressions]
            }

            with open(self.path, "w") as f:
                yaml.dump(data, f, default_flow_style=False, sort_keys=False)

            logger.info(f"Saved {len(self._suppressions)} suppressions to {self.path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save suppressions: {e}")
            return False

    def add(
        self,
        source_pattern: str,
        target_pattern: str,
        reason: str = "",
        created_by: str = "user",
        expires_at: datetime | None = None,
    ) -> Suppression:
        """
        Add a new suppression.
        
        Args:
            source_pattern: Glob pattern for source
            target_pattern: Glob pattern for target
            reason: Why this suppression exists
            created_by: Who created it
            expires_at: Optional expiration datetime
        
        Returns:
            The created Suppression
        """
        if not self._loaded:
            self.load()

        suppression = Suppression(
            source_pattern=source_pattern,
            target_pattern=target_pattern,
            reason=reason,
            created_by=created_by,
            expires_at=expires_at,
        )

        self._suppressions.append(suppression)
        logger.info(f"Added suppression: {source_pattern} → {target_pattern}")

        return suppression

    def remove(self, suppression_id: str) -> bool:
        """
        Remove a suppression by ID.
        
        Args:
            suppression_id: ID of suppression to remove
        
        Returns:
            True if removed, False if not found
        """
        if not self._loaded:
            self.load()

        for i, s in enumerate(self._suppressions):
            if s.id == suppression_id:
                removed = self._suppressions.pop(i)
                logger.info(f"Removed suppression: {removed.source_pattern} → {removed.target_pattern}")
                return True

        logger.warning(f"Suppression not found: {suppression_id}")
        return False

    def remove_by_index(self, index: int) -> bool:
        """
        Remove a suppression by list index (1-based for CLI friendliness).
        
        Args:
            index: 1-based index
        
        Returns:
            True if removed
        """
        if not self._loaded:
            self.load()

        zero_index = index - 1
        if 0 <= zero_index < len(self._suppressions):
            removed = self._suppressions.pop(zero_index)
            logger.info(f"Removed suppression #{index}: {removed.source_pattern} → {removed.target_pattern}")
            return True

        logger.warning(f"Invalid suppression index: {index}")
        return False

    def list(self, include_expired: bool = False) -> List[Suppression]:
        """
        List all suppressions.
        
        Args:
            include_expired: Whether to include expired suppressions
        
        Returns:
            List of suppressions
        """
        if not self._loaded:
            self.load()

        if include_expired:
            return list(self._suppressions)

        return [s for s in self._suppressions if not s.is_expired()]

    def is_suppressed(self, source_id: str, target_id: str) -> SuppressionMatch:
        """
        Check if an edge should be suppressed.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
        
        Returns:
            SuppressionMatch with result and details
        """
        if not self._loaded:
            self.load()

        for suppression in self._suppressions:
            if suppression.matches(source_id, target_id):
                logger.debug(
                    f"Suppressed: {source_id} → {target_id} "
                    f"(pattern: {suppression.source_pattern} → {suppression.target_pattern})"
                )
                return SuppressionMatch(
                    suppressed=True,
                    suppression=suppression,
                    reason=suppression.reason or "Matched suppression rule",
                )

        return SuppressionMatch(suppressed=False)

    def get_by_id(self, suppression_id: str) -> Suppression | None:
        """Get a suppression by ID."""
        if not self._loaded:
            self.load()

        for s in self._suppressions:
            if s.id == suppression_id:
                return s
        return None

    def clear_expired(self) -> int:
        """
        Remove all expired suppressions.
        
        Returns:
            Number of suppressions removed
        """
        if not self._loaded:
            self.load()

        original_count = len(self._suppressions)
        self._suppressions = [s for s in self._suppressions if not s.is_expired()]
        removed = original_count - len(self._suppressions)

        if removed > 0:
            logger.info(f"Cleared {removed} expired suppressions")

        return removed

    def find_matching(self, source_id: str, target_id: str) -> List[Suppression]:
        """
        Find all suppressions that match a source/target pair.
        
        Useful for debugging why something is/isn't suppressed.
        """
        if not self._loaded:
            self.load()

        return [s for s in self._suppressions if s.matches(source_id, target_id)]

    @property
    def count(self) -> int:
        """Number of suppressions."""
        if not self._loaded:
            self.load()
        return len(self._suppressions)

    @property
    def active_count(self) -> int:
        """Number of active (non-expired) suppressions."""
        if not self._loaded:
            self.load()
        return len([s for s in self._suppressions if s.is_active()])


def create_default_store(path: Path | None = None) -> SuppressionStore:
    """
    Create a SuppressionStore and load from disk.
    
    Args:
        path: Optional path to YAML file
    
    Returns:
        Initialized SuppressionStore
    """
    store = SuppressionStore(path)
    store.load()
    return store


class SuppressionAwareStitcher:
    """
    Mixin/wrapper for adding suppression awareness to stitching.
    
    This class wraps the Edge creation process to check suppressions.
    """

    def __init__(self, store: SuppressionStore | None = None):
        """
        Initialize with a suppression store.
        
        Args:
            store: SuppressionStore instance (creates default if None)
        """
        self.store = store or create_default_store()
        self._suppressed_count = 0
        self._suppressed_edges: List[Dict[str, Any]] = []

    def should_create_edge(self, source_id: str, target_id: str) -> bool:
        """
        Check if an edge should be created (not suppressed).
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
        
        Returns:
            True if edge should be created
        """
        match = self.store.is_suppressed(source_id, target_id)

        if match.suppressed:
            self._suppressed_count += 1
            self._suppressed_edges.append({
                "source_id": source_id,
                "target_id": target_id,
                "reason": match.reason,
                "pattern": f"{match.suppression.source_pattern} → {match.suppression.target_pattern}" if match.suppression else "",
            })
            return False

        return True

    def reset_stats(self) -> None:
        """Reset suppression statistics."""
        self._suppressed_count = 0
        self._suppressed_edges = []

    @property
    def suppressed_count(self) -> int:
        """Number of edges suppressed in current session."""
        return self._suppressed_count

    @property
    def suppressed_edges(self) -> List[Dict[str, Any]]:
        """List of suppressed edges with details."""
        return list(self._suppressed_edges)
