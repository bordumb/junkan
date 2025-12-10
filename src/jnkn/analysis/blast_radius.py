"""
Blast Radius Analysis Engine.
"""

from typing import List, Dict, Any
from ..core.interfaces import IGraph

class BlastRadiusAnalyzer:
    """
    Calculates downstream impact of changes.
    """
    def __init__(self, graph: IGraph):
        self.graph = graph

    def calculate(self, source_node_ids: List[str], max_depth: int = -1) -> Dict[str, Any]:
        """
        Identify all nodes that would be impacted if source_nodes changed.
        """
        # Delegate semantic traversal to the graph implementation
        impacted_ids = self.graph.get_impacted_nodes(source_node_ids, max_depth)
        
        # Sort for deterministic output
        sorted_impacted = sorted(list(impacted_ids))
        
        return {
            "source_artifacts": source_node_ids,
            "impacted_artifacts": sorted_impacted,
            "count": len(sorted_impacted)
        }