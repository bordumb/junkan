"""
Storage adapter interface.

Defines the contract that all storage backends must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from ..graph import DependencyGraph
from ..types import Edge, Node, ScanMetadata


class StorageAdapter(ABC):
    """
    Abstract interface for persistence strategies.

    Implementations must provide:
    - Node and edge persistence
    - Graph hydration (loading)
    - Incremental scan support via file metadata
    - Batch operations for performance
    """

    @abstractmethod
    def save_node(self, node: Node) -> None:
        """Persist a single node."""
        pass

    @abstractmethod
    def save_nodes_batch(self, nodes: List[Node]) -> int:
        """Persist multiple nodes in a single transaction."""
        pass

    @abstractmethod
    def save_edge(self, edge: Edge) -> None:
        """Persist a single edge."""
        pass

    @abstractmethod
    def save_edges_batch(self, edges: List[Edge]) -> int:
        """Persist multiple edges in a single transaction."""
        pass

    @abstractmethod
    def load_node(self, node_id: str) -> Node | None:
        """Load a node by ID."""
        pass

    @abstractmethod
    def load_all_nodes(self) -> List[Node]:
        """Load all nodes from storage."""
        pass

    @abstractmethod
    def load_all_edges(self) -> List[Edge]:
        """Load all edges from storage."""
        pass

    @abstractmethod
    def load_graph(self) -> DependencyGraph:
        """Hydrate a full DependencyGraph from storage."""
        pass

    @abstractmethod
    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its associated edges."""
        pass

    @abstractmethod
    def delete_nodes_by_file(self, file_path: str) -> int:
        """Delete all nodes originating from a file."""
        pass

    @abstractmethod
    def delete_edges_by_source(self, source_id: str) -> int:
        """Delete all edges from a source node."""
        pass

    @abstractmethod
    def save_scan_metadata(self, metadata: ScanMetadata) -> None:
        """Save file scan metadata for incremental scanning."""
        pass

    @abstractmethod
    def get_scan_metadata(self, file_path: str) -> ScanMetadata | None:
        """Get scan metadata for a file."""
        pass

    @abstractmethod
    def get_all_scan_metadata(self) -> List[ScanMetadata]:
        """Get scan metadata for all files."""
        pass

    @abstractmethod
    def delete_scan_metadata(self, file_path: str) -> bool:
        """Delete scan metadata for a file."""
        pass

    @abstractmethod
    def query_descendants(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query all descendants of a node."""
        pass

    @abstractmethod
    def query_ancestors(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query all ancestors of a node."""
        pass

    @abstractmethod
    def get_schema_version(self) -> int:
        """Get the current schema version."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all data from storage."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Close any open connections."""
        pass
