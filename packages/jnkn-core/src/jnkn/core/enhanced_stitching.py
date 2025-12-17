"""
Enhanced Stitching Module with Explicit Mapping Support (Phase 3).

This module extends the core stitching functionality to integrate explicit
user-defined mappings, giving them highest priority over fuzzy matching.

Integration Flow:
    1. Apply explicit mappings first (100% confidence)
    2. Mark ignored nodes to skip fuzzy matching
    3. Run fuzzy matching rules on remaining nodes
    4. Apply framework pack boosts/suppressions
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Set

from .graph import DependencyGraph
from .manifest import ExplicitMapping, MappingType, ProjectManifest
from .mappings import MappingMatcher
from .types import Edge, RelationshipType

logger = logging.getLogger(__name__)


@dataclass
class StitchingResult:
    """
    Result of the stitching process.

    Attributes:
        edges: List of edges to add to the graph.
        explicit_count: Number of edges from explicit mappings.
        fuzzy_count: Number of edges from fuzzy matching.
        ignored_count: Number of nodes marked as ignored.
        filtered_count: Number of edges filtered by confidence threshold.
    """

    edges: List[Edge]
    explicit_count: int = 0
    fuzzy_count: int = 0
    ignored_count: int = 0
    filtered_count: int = 0

    @property
    def total(self) -> int:
        """Total edges created."""
        return len(self.edges)


class EnhancedStitcher:
    """
    Cross-domain dependency stitcher with explicit mapping support.

    Combines explicit user-defined mappings with fuzzy matching rules
    to create a complete set of cross-domain edges.

    Priority order:
    1. Explicit mappings (always win, 100% confidence)
    2. Framework pack boosts/suppressions
    3. Fuzzy matching rules

    Example:
        ```python
        stitcher = EnhancedStitcher.from_project(Path("."))
        result = stitcher.stitch(graph)
        storage.save_edges_batch(result.edges)
        ```
    """

    def __init__(
        self,
        mappings: List[ExplicitMapping] | None = None,
        min_confidence: float = 0.5,
    ):
        """
        Initialize the stitcher.

        Args:
            mappings: Explicit mappings from jnkn.toml.
            min_confidence: Minimum confidence threshold for fuzzy matches.
        """
        self.mappings = mappings or []
        self.min_confidence = min_confidence
        self.matcher = MappingMatcher(self.mappings) if self.mappings else None

        # Import rules lazily to avoid circular imports
        self._rules = None

    @classmethod
    def from_project(cls, project_root: Path, min_confidence: float = 0.5) -> "EnhancedStitcher":
        """
        Create stitcher from project configuration.

        Args:
            project_root: Path to project root containing jnkn.toml.
            min_confidence: Minimum confidence threshold.

        Returns:
            Configured EnhancedStitcher instance.
        """
        manifest_path = project_root / "jnkn.toml"
        manifest = ProjectManifest.load(manifest_path)

        return cls(
            mappings=manifest.mappings,
            min_confidence=min_confidence,
        )

    def _get_rules(self):
        """Lazy load stitching rules to avoid circular imports."""
        if self._rules is None:
            from .stitching import EnvVarToInfraRule, InfraToInfraRule, MatchConfig

            self._rules = [
                EnvVarToInfraRule(MatchConfig()),
                InfraToInfraRule(MatchConfig()),
            ]
        return self._rules

    def stitch(self, graph: DependencyGraph) -> StitchingResult:
        """
        Run the complete stitching process.

        Args:
            graph: The dependency graph to stitch.

        Returns:
            StitchingResult with all created edges.
        """
        result = StitchingResult(edges=[])

        # Track which targets have been explicitly mapped
        explicitly_mapped_targets: Set[str] = set()
        ignored_sources: Set[str] = set()

        # 1. Apply explicit mappings first (highest priority)
        if self.matcher:
            explicit_edges = self._apply_explicit_mappings(graph)
            for edge in explicit_edges:
                explicitly_mapped_targets.add(edge.target_id)
                result.edges.append(edge)
            result.explicit_count = len(explicit_edges)

            # Track ignored sources
            for mapping in self.mappings:
                if mapping.mapping_type == MappingType.IGNORE:
                    ignored_sources.add(mapping.source)
            result.ignored_count = len(ignored_sources)

        # 2. Run fuzzy matching rules
        fuzzy_edges = self._apply_fuzzy_rules(
            graph,
            explicitly_mapped_targets,
            ignored_sources,
        )

        # 3. Filter by confidence threshold
        filtered_count = 0
        for edge in fuzzy_edges:
            if (edge.confidence or 0.5) >= self.min_confidence:
                result.edges.append(edge)
            else:
                filtered_count += 1

        result.fuzzy_count = len(fuzzy_edges) - filtered_count
        result.filtered_count = filtered_count

        return result

    def _apply_explicit_mappings(self, graph: DependencyGraph) -> List[Edge]:
        """
        Create edges from explicit mappings.

        Args:
            graph: The dependency graph.

        Returns:
            List of edges from explicit mappings.
        """
        edges = []
        node_ids = {n.id for n in graph.iter_nodes()}

        # Handle exact mappings
        for mapping in self.mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                continue

            # Check if both source and target exist
            source_exists = mapping.source in node_ids
            target_exists = mapping.target in node_ids

            if source_exists and target_exists:
                edge = Edge(
                    source_id=mapping.source,
                    target_id=mapping.target,
                    type=RelationshipType.PROVIDES,
                    confidence=1.0,  # Explicit = full confidence
                    metadata={
                        "rule": "explicit_mapping",
                        "mapping_type": mapping.mapping_type.value,
                        "reason": mapping.reason,
                    },
                )
                edges.append(edge)
                logger.debug(f"Created explicit edge: {mapping.source} -> {mapping.target}")
            elif "*" in mapping.source or "*" in mapping.target:
                # Pattern mapping - expand it
                expanded = self.matcher.expand_patterns(node_ids)
                for match in expanded:
                    if match.mapping.source == mapping.source:
                        edge = Edge(
                            source_id=match.source_id,
                            target_id=match.target_id,
                            type=RelationshipType.PROVIDES,
                            confidence=1.0,
                            metadata=match.to_edge_metadata(),
                        )
                        edges.append(edge)

        return edges

    def _apply_fuzzy_rules(
        self,
        graph: DependencyGraph,
        skip_targets: Set[str],
        skip_sources: Set[str],
    ) -> List[Edge]:
        """
        Run fuzzy matching rules, skipping explicitly mapped nodes.

        Args:
            graph: The dependency graph.
            skip_targets: Target node IDs to skip (already mapped).
            skip_sources: Source node IDs to skip (ignored).

        Returns:
            List of fuzzy-matched edges.
        """
        edges = []
        rules = self._get_rules()

        for rule in rules:
            plan = rule.plan(graph)

            for edge in plan.edges_to_add:
                # Skip if target is already explicitly mapped
                if edge.target_id in skip_targets:
                    continue

                # Skip if source is ignored
                if edge.source_id in skip_sources:
                    continue

                # Also check if source matches an ignore pattern
                if self.matcher and self.matcher.is_ignored(edge.source_id):
                    continue

                edges.append(edge)

        return edges

    def check_mapping_conflicts(
        self,
        graph: DependencyGraph,
    ) -> List[str]:
        """
        Check for conflicts between explicit and fuzzy matches.

        Args:
            graph: The dependency graph.

        Returns:
            List of conflict descriptions.
        """
        conflicts = []

        if not self.matcher:
            return conflicts

        # Get fuzzy matches
        rules = self._get_rules()
        fuzzy_edges = {}

        for rule in rules:
            plan = rule.plan(graph)
            for edge in plan.edges_to_add:
                key = (edge.source_id, edge.target_id)
                fuzzy_edges[key] = edge

        # Check for overrides
        for mapping in self.mappings:
            if mapping.mapping_type == MappingType.IGNORE:
                continue

            # See if fuzzy would have matched differently
            explicit_key = (mapping.source, mapping.target)

            # Find any fuzzy edge with same source but different target
            for (source, target), edge in fuzzy_edges.items():
                if source == mapping.source and target != mapping.target:
                    conflicts.append(
                        f"Explicit mapping overrides fuzzy: "
                        f"{source} -> {mapping.target} (fuzzy would be: {target})"
                    )

        return conflicts


def create_enhanced_stitcher(
    project_root: Optional[Path] = None,
    min_confidence: float = 0.5,
) -> EnhancedStitcher:
    """
    Factory function to create an EnhancedStitcher.

    Args:
        project_root: Project root path (uses cwd if None).
        min_confidence: Minimum confidence threshold.

    Returns:
        Configured EnhancedStitcher instance.
    """
    root = project_root or Path.cwd()
    return EnhancedStitcher.from_project(root, min_confidence)
