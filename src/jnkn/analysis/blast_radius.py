"""
Blast Radius Analysis.

Calculates the downstream impact of changes to artifacts.
Supports both in-memory graph traversal and lazy SQL-based queries.
"""

from typing import Dict, List, Any, Optional, Set
from ..core.graph import DependencyGraph
from ..core.storage.base import StorageAdapter


class BlastRadiusAnalyzer:
    """
    Analyzes the downstream impact of changing specific artifacts.
    
    Supports two modes:
    1. In-memory: Uses loaded DependencyGraph (faster for small graphs)
    2. Lazy: Uses storage adapter's CTE queries (memory-efficient)
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
        
        Args:
            changed_artifacts: List of artifact IDs or partial paths
            max_depth: Maximum traversal depth (-1 for unlimited)
            min_confidence: Minimum edge confidence to follow
            
        Returns:
            Dictionary with impact analysis results
        """
        unique_downstream: Set[str] = set()
        
        for root_id in changed_artifacts:
            descendants = self._get_descendants(root_id, max_depth)
            unique_downstream.update(descendants)
        
        breakdown = self._categorize(unique_downstream)
        
        return {
            "source_artifacts": changed_artifacts,
            "total_impacted_count": len(unique_downstream),
            "impacted_artifacts": sorted(unique_downstream),
            "breakdown": breakdown,
        }
    
    def _get_descendants(self, node_id: str, max_depth: int) -> Set[str]:
        """Get descendants using available method."""
        # Try exact ID first
        descendants = self._query_descendants(node_id, max_depth)
        
        if not descendants:
            # Try as file path
            file_id = f"file://{node_id}"
            descendants = self._query_descendants(file_id, max_depth)
        
        if not descendants:
            # Try as env var
            env_id = f"env:{node_id}"
            descendants = self._query_descendants(env_id, max_depth)
        
        if not descendants:
            # Try as infra resource
            infra_id = f"infra:{node_id}"
            descendants = self._query_descendants(infra_id, max_depth)
        
        return descendants
    
    def _query_descendants(self, node_id: str, max_depth: int) -> Set[str]:
        """Query descendants from graph or storage."""
        if self.graph:
            if not self.graph.has_node(node_id):
                return set()
            return self.graph.get_descendants(node_id)
        
        if self.storage:
            return set(self.storage.query_descendants(node_id, max_depth))
        
        return set()
    
    def _categorize(self, artifacts: Set[str]) -> Dict[str, List[str]]:
        """Categorize artifacts by type."""
        breakdown: Dict[str, List[str]] = {
            "infra": [],
            "data": [],
            "code": [],
            "env": [],
            "unknown": [],
        }
        
        for art in artifacts:
            if art.startswith("infra:"):
                breakdown["infra"].append(art)
            elif art.startswith("env:"):
                breakdown["env"].append(art)
            elif art.startswith("file://"):
                breakdown["code"].append(art)
            elif any(x in art for x in ["table", "model", "view", "topic"]):
                breakdown["data"].append(art)
            else:
                breakdown["unknown"].append(art)
        
        return breakdown
    
    def get_impact_path(
        self,
        source: str,
        target: str
    ) -> Optional[List[str]]:
        """
        Find the shortest impact path between source and target.
        
        Useful for understanding *why* a change impacts a downstream artifact.
        """
        if not self.graph:
            return None
        
        import networkx as nx
        
        try:
            path = nx.shortest_path(
                self.graph._graph,
                source=source,
                target=target
            )
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None