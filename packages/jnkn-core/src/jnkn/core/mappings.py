"""
Explicit Mappings System (Phase 3).

Provides user-defined mappings between artifacts in the dependency graph,
allowing overrides when fuzzy matching fails or produces incorrect results.

Features:
    - Exact mappings: `"infra:output:db_endpoint" = "env:DATABASE_URL"`
    - Pattern mappings: `"infra:output:redis_*" = "env:REDIS_*"`
    - Ignore mappings: `"env:CI_BUILD_NUMBER" = { ignore = true }`

Pattern Matching:
    Supports glob-style wildcards (*) for flexible matching across
    multiple similar artifacts.
"""

from __future__ import annotations

import fnmatch
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from .manifest import ExplicitMapping, MappingType, ProjectManifest

logger = logging.getLogger(__name__)


@dataclass
class MappingMatch:
    """
    Result of matching a mapping pattern against node IDs.

    Attributes:
        source_id: Matched source node ID.
        target_id: Matched target node ID.
        mapping: The explicit mapping that produced this match.
        confidence: Always 1.0 for explicit mappings.
    """

    source_id: str
    target_id: str
    mapping: ExplicitMapping
    confidence: float = 1.0

    @property
    def is_ignore(self) -> bool:
        """Check if this is an ignore mapping."""
        return self.mapping.mapping_type == MappingType.IGNORE

    def to_edge_metadata(self) -> Dict[str, Any]:
        """
        Generate metadata for the resulting edge.

        Returns:
            Dictionary with mapping metadata.
        """
        return {
            "rule": "explicit_mapping",
            "mapping_type": self.mapping.mapping_type.value,
            "reason": self.mapping.reason,
            "source_pattern": self.mapping.source,
            "target_pattern": self.mapping.target,
        }


class MappingMatcher:
    """
    Matches explicit mappings against node IDs with glob pattern support.

    Handles both exact matches and wildcard patterns, expanding patterns
    into concrete node pairs when given a set of available node IDs.

    Example:
        ```python
        matcher = MappingMatcher(mappings)

        # Check if a specific pair has an explicit mapping
        if match := matcher.match("infra:output:db_url", "env:DATABASE_URL"):
            print(f"Explicit mapping found: {match.mapping.reason}")

        # Expand pattern mappings against available nodes
        all_matches = matcher.expand_patterns(available_node_ids)
        ```
    """

    def __init__(self, mappings: List[ExplicitMapping]):
        """
        Initialize the matcher.

        Args:
            mappings: List of explicit mappings from manifest.
        """
        self.mappings = mappings
        self._exact_source_map: Dict[str, ExplicitMapping] = {}
        self._pattern_mappings: List[ExplicitMapping] = []
        self._ignored_sources: Set[str] = set()

        self._index_mappings()

    def _index_mappings(self) -> None:
        """Build indexes for fast lookup."""
        for mapping in self.mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                self._ignored_sources.add(mapping.source)
            elif self._has_wildcard(mapping.source) or self._has_wildcard(mapping.target):
                self._pattern_mappings.append(mapping)
            else:
                self._exact_source_map[mapping.source] = mapping

    @staticmethod
    def _has_wildcard(pattern: str) -> bool:
        """Check if a pattern contains wildcards."""
        return "*" in pattern or "?" in pattern

    def is_ignored(self, source_id: str) -> bool:
        """
        Check if a source node should be ignored.

        Args:
            source_id: Node ID to check.

        Returns:
            True if the node has an ignore mapping.
        """
        # Exact match
        if source_id in self._ignored_sources:
            return True

        # Pattern match
        for mapping in self.mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                if fnmatch.fnmatch(source_id, mapping.source):
                    return True

        return False

    def get_ignore_reason(self, source_id: str) -> Optional[str]:
        """
        Get the reason for ignoring a source node.

        Args:
            source_id: Node ID to check.

        Returns:
            Reason string if ignored, None otherwise.
        """
        for mapping in self.mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                if source_id == mapping.source or fnmatch.fnmatch(source_id, mapping.source):
                    return mapping.reason
        return None

    def match(self, source_id: str, target_id: str) -> Optional[MappingMatch]:
        """
        Check if an explicit mapping exists for a source-target pair.

        Args:
            source_id: Source node ID.
            target_id: Target node ID.

        Returns:
            MappingMatch if found, None otherwise.
        """
        # 1. Check exact match
        if source_id in self._exact_source_map:
            mapping = self._exact_source_map[source_id]
            if mapping.target == target_id:
                return MappingMatch(
                    source_id=source_id,
                    target_id=target_id,
                    mapping=mapping,
                )

        # 2. Check pattern matches
        for mapping in self._pattern_mappings:
            if self._matches_pattern(source_id, target_id, mapping):
                return MappingMatch(
                    source_id=source_id,
                    target_id=target_id,
                    mapping=mapping,
                )

        return None

    def _matches_pattern(
        self,
        source_id: str,
        target_id: str,
        mapping: ExplicitMapping,
    ) -> bool:
        """
        Check if source and target match a pattern mapping.

        For wildcard patterns, extracts the wildcard portion from source
        and verifies it matches the corresponding position in target.
        """
        # Source must match the source pattern
        if not fnmatch.fnmatch(source_id, mapping.source):
            return False

        # For patterns with wildcards in both source and target,
        # extract the matched portion and verify it matches in target
        if "*" in mapping.source and "*" in mapping.target:
            # Extract the wildcard match from source
            wildcard_value = self._extract_wildcard_match(source_id, mapping.source)
            if wildcard_value:
                # Build expected target by substituting wildcard
                expected_target = mapping.target.replace("*", wildcard_value)
                return target_id == expected_target

        # Simple pattern match on target
        return fnmatch.fnmatch(target_id, mapping.target)

    @staticmethod
    def _extract_wildcard_match(value: str, pattern: str) -> Optional[str]:
        """
        Extract the portion of value that matches the wildcard in pattern.

        Args:
            value: Concrete string (e.g., "infra:output:redis_url").
            pattern: Pattern with wildcard (e.g., "infra:output:redis_*").

        Returns:
            The matched portion (e.g., "url"), or None if no match.
        """
        if "*" not in pattern:
            return None

        # Convert glob to regex
        regex_pattern = pattern.replace("*", "(.*)")
        regex_pattern = regex_pattern.replace("?", "(.)")

        match = re.match(f"^{regex_pattern}$", value)
        if match:
            return match.group(1)
        return None

    def expand_patterns(
        self,
        node_ids: Set[str],
    ) -> List[MappingMatch]:
        """
        Expand pattern mappings against available nodes.

        Given a set of node IDs, finds all concrete source-target pairs
        that match pattern mappings.

        Args:
            node_ids: Set of available node IDs in the graph.

        Returns:
            List of MappingMatch objects for all expanded patterns.
        """
        matches = []

        for mapping in self._pattern_mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                continue

            # Find all source nodes matching the pattern
            matching_sources = [nid for nid in node_ids if fnmatch.fnmatch(nid, mapping.source)]

            for source_id in matching_sources:
                # Extract wildcard value
                wildcard_value = self._extract_wildcard_match(source_id, mapping.source)

                if wildcard_value and "*" in mapping.target:
                    # Build expected target
                    expected_target = mapping.target.replace("*", wildcard_value)

                    # Check if target exists
                    if expected_target in node_ids:
                        matches.append(
                            MappingMatch(
                                source_id=source_id,
                                target_id=expected_target,
                                mapping=mapping,
                            )
                        )
                elif "*" not in mapping.target:
                    # Fixed target
                    if mapping.target in node_ids:
                        matches.append(
                            MappingMatch(
                                source_id=source_id,
                                target_id=mapping.target,
                                mapping=mapping,
                            )
                        )

        return matches

    def get_explicit_target(self, source_id: str) -> Optional[str]:
        """
        Get the explicit target for a source node.

        Args:
            source_id: Source node ID.

        Returns:
            Target node ID if an exact mapping exists, None otherwise.
        """
        if source_id in self._exact_source_map:
            return self._exact_source_map[source_id].target
        return None

    def iter_exact_mappings(self) -> Iterator[ExplicitMapping]:
        """Iterate over non-pattern mappings."""
        for mapping in self.mappings:
            if not self._has_wildcard(mapping.source) and not self._has_wildcard(mapping.target):
                yield mapping


@dataclass
class MappingValidationWarning:
    """
    Warning from mapping validation.

    Attributes:
        code: Warning code for categorization.
        message: Human-readable warning message.
        suggestion: Suggested fix or action.
        severity: Warning severity level.
    """

    code: str
    message: str
    suggestion: str = ""
    severity: str = "warning"


class MappingValidator:
    """
    Validates explicit mappings against the dependency graph.

    Checks for:
    - Missing source nodes
    - Missing target nodes
    - Redundant mappings (fuzzy would match anyway)
    - Conflicting mappings
    """

    def __init__(self, node_ids: Set[str]):
        """
        Initialize validator.

        Args:
            node_ids: Set of node IDs in the current graph.
        """
        self.node_ids = node_ids

    def validate(self, mappings: List[ExplicitMapping]) -> List[MappingValidationWarning]:
        """
        Validate all mappings.

        Args:
            mappings: List of explicit mappings to validate.

        Returns:
            List of validation warnings.
        """
        warnings = []

        for mapping in mappings:
            # Skip ignore mappings - they don't need targets
            if mapping.mapping_type == MappingType.IGNORE:
                continue

            # Check source exists (for non-pattern mappings)
            if "*" not in mapping.source:
                if mapping.source not in self.node_ids:
                    warnings.append(
                        MappingValidationWarning(
                            code="mapping-source-not-found",
                            message=f"Mapping source '{mapping.source}' not found in graph",
                            suggestion="Check the node ID or run 'jnkn scan' first",
                        )
                    )

            # Check target exists (for non-pattern mappings)
            if "*" not in mapping.target:
                if mapping.target not in self.node_ids:
                    warnings.append(
                        MappingValidationWarning(
                            code="mapping-target-not-found",
                            message=f"Mapping target '{mapping.target}' not found in graph",
                            suggestion="Check the node ID or ensure the file is being scanned",
                        )
                    )

        # Check for conflicts
        conflicts = self._find_conflicts(mappings)
        warnings.extend(conflicts)

        return warnings

    def _find_conflicts(self, mappings: List[ExplicitMapping]) -> List[MappingValidationWarning]:
        """Find conflicting mappings (same source, different targets)."""
        warnings = []
        source_to_targets: Dict[str, List[str]] = {}

        for mapping in mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                continue

            if mapping.source not in source_to_targets:
                source_to_targets[mapping.source] = []
            source_to_targets[mapping.source].append(mapping.target)

        for source, targets in source_to_targets.items():
            if len(targets) > 1:
                warnings.append(
                    MappingValidationWarning(
                        code="conflicting-mappings",
                        message=f"Source '{source}' has multiple targets: {targets}",
                        suggestion="Remove duplicate mappings or use a single target",
                        severity="error",
                    )
                )

        return warnings


def load_mappings_from_manifest(project_root: Path) -> MappingMatcher:
    """
    Load mappings from jnkn.toml and create a matcher.

    Args:
        project_root: Root directory containing jnkn.toml.

    Returns:
        MappingMatcher instance.
    """
    manifest_path = project_root / "jnkn.toml"
    manifest = ProjectManifest.load(manifest_path)
    return MappingMatcher(manifest.mappings)


def suggest_mappings(
    orphan_sources: List[str],
    potential_targets: List[str],
    min_confidence: float = 0.5,
) -> List[Tuple[str, str, float]]:
    """
    Suggest mappings for orphaned source nodes.

    Uses simple name similarity to suggest potential matches.

    Args:
        orphan_sources: List of orphan source node IDs.
        potential_targets: List of potential target node IDs.
        min_confidence: Minimum confidence threshold.

    Returns:
        List of (source, target, confidence) tuples.
    """
    suggestions = []

    for source in orphan_sources:
        source_name = _extract_name(source)
        source_tokens = _tokenize(source_name)

        best_match = None
        best_score = 0.0

        for target in potential_targets:
            target_name = _extract_name(target)
            target_tokens = _tokenize(target_name)

            score = _calculate_token_overlap(source_tokens, target_tokens)
            if score > best_score and score >= min_confidence:
                best_score = score
                best_match = target

        if best_match:
            suggestions.append((source, best_match, best_score))

    return suggestions


def _extract_name(node_id: str) -> str:
    """Extract the name portion from a node ID."""
    if "://" in node_id:
        return node_id.split("://", 1)[1]
    if ":" in node_id:
        parts = node_id.split(":")
        return parts[-1]
    return node_id


def _tokenize(name: str) -> Set[str]:
    """Split name into tokens."""
    normalized = name.lower()
    for sep in ["_", ".", "-", "/", ":"]:
        normalized = normalized.replace(sep, " ")
    return {t.strip() for t in normalized.split() if t.strip() and len(t.strip()) > 2}


def _calculate_token_overlap(tokens1: Set[str], tokens2: Set[str]) -> float:
    """Calculate Jaccard similarity between token sets."""
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1 & tokens2
    union = tokens1 | tokens2
    return len(intersection) / len(union) if union else 0.0
