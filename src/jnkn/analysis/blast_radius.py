"""
Blast Radius Analysis.

Calculates the downstream impact of changes to artifacts.
Supports both in-memory graph traversal and lazy SQL-based queries.
"""

from typing import Any, Dict, List, Optional, Set

from ..core.graph import DependencyGraph
from ..core.storage.base import StorageAdapter


class BlastRadiusAnalyzer:
    """
    Analyzes the downstream impact of changing specific artifacts.
    """

    def __init__(
        self,
        graph: Optional[DependencyGraph] = None,
        storage: Optional[StorageAdapter] = None
    ):
        self.graph = graph
        self.storage = storage

    def calculate(
        self,
        changed_artifacts: List[str],
        max_depth: int = -1,
        min_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Calculate the blast radius for a list of changed artifacts.
        """
        unique_downstream: Set[str] = set()

        for root_id in changed_artifacts:
            # Use semantic impact analysis
            impacted = self._get_impacted(root_id, max_depth)
            unique_downstream.update(impacted)

        breakdown = self._categorize(unique_downstream)

        return {
            "source_artifacts": changed_artifacts,
            "total_impacted_count": len(unique_downstream),
            "impacted_artifacts": sorted(unique_downstream),
            "breakdown": breakdown,
        }

    def _get_impacted(self, node_id: str, max_depth: int) -> Set[str]:
        """Get impacted nodes using available method."""
        # Try exact ID first
        impacted = self._query_impact(node_id, max_depth)

        if not impacted:
            # Try prefixes if exact ID failed
            for prefix in ["file://", "env:", "infra:", "data:"]:
                if not node_id.startswith(prefix):
                    candidate = f"{prefix}{node_id}"
                    found = self._query_impact(candidate, max_depth)
                    if found:
                        return found

        return impacted

    def _query_impact(self, node_id: str, max_depth: int) -> Set[str]:
        """Query impact from graph or storage."""
        if self.graph:
            if not self.graph.has_node(node_id):
                return set()
            # Use the new semantic traversal method
            return self.graph.get_impacted_nodes(node_id, max_depth)

        if self.storage:
            # TODO: Implement semantic SQL traversal in SQLiteStorage
            # Fallback to simple descendants for now if graph not loaded
            return set(self.storage.query_descendants(node_id, max_depth))

        return set()

    def _categorize(self, artifacts: Set[str]) -> Dict[str, List[str]]:
        """Categorize artifacts by type."""
        breakdown: Dict[str, List[str]] = {
            "infra": [],
            "data": [],
            "code": [],
            "config": [],
            "kubernetes": [],
            "other": [],
        }

        for art in artifacts:
            if art.startswith("infra:"):
                breakdown["infra"].append(art)
            elif art.startswith("env:"):
                breakdown["config"].append(art)
            elif art.startswith("file:") or art.startswith("entity:"):
                breakdown["code"].append(art)
            elif art.startswith("data:") or "table" in art:
                breakdown["data"].append(art)
            elif art.startswith("k8s:"):
                breakdown["kubernetes"].append(art)
            else:
                breakdown["other"].append(art)

        return breakdown