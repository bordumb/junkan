"""
Core Interfaces for the Jnkn Architecture.

Defines the contracts for:
1. Graph Storage/Logic (IGraph) - Decouples analysis from rustworkx/networkx.
2. Parsers (IParser) - Ensures strict return types for all language parsers.
"""

from typing import Protocol, List, Optional, Any, Iterator, Union, Set
from pathlib import Path

from .types import Node, Edge


class IGraph(Protocol):
    """
    Abstract interface for the Dependency Graph.
    
    Any underlying graph implementation (rustworkx, networkx, Neo4j adapter)
    must satisfy this contract to be used by the Analysis engine.
    """

    @property
    def node_count(self) -> int:
        """Return total number of nodes."""
        ...

    @property
    def edge_count(self) -> int:
        """Return total number of edges."""
        ...

    def add_node(self, node: Node) -> None:
        """Add or update a node in the graph."""
        ...

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge between two nodes."""
        ...

    def get_node(self, node_id: str) -> Optional[Node]:
        """Retrieve a node by its ID."""
        ...

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        ...
        
    def has_edge(self, source_id: str, target_id: str) -> bool:
        """Check if an edge exists between two nodes."""
        ...

    def remove_node(self, node_id: str) -> None:
        """Remove a node and its incident edges."""
        ...

    def find_nodes(self, pattern: str) -> List[str]:
        """
        Fuzzy search for node IDs matching a pattern/substring.
        Returns a list of matching Node IDs.
        """
        ...

    def get_out_edges(self, node_id: str) -> List[Edge]:
        """Get all outgoing edges from this node."""
        ...

    def get_in_edges(self, node_id: str) -> List[Edge]:
        """Get all incoming edges to this node."""
        ...

    def iter_nodes(self) -> Iterator[Node]:
        """Iterate over all nodes."""
        ...

    def iter_edges(self) -> Iterator[Edge]:
        """Iterate over all edges."""
        ...

    def trace(self, source_id: str, target_id: str) -> List[List[str]]:
        """
        Find all simple paths between source and target.
        Returns list of paths (each path is a list of node IDs).
        """
        ...

    def get_descendants(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """Get all downstream node IDs reachable from the source."""
        ...
        
    def get_ancestors(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """Get all upstream node IDs that point to the source."""
        ...

    def get_impacted_nodes(self, source_ids: List[str], max_depth: int = -1) -> Set[str]:
        """
        Calculate the "Blast Radius" or semantic impact of changing specific nodes.
        
        Unlike simple descendants, this traverses:
        - Downstream for data flow (PROVIDES, WRITES)
        - Upstream for dependencies (READS, DEPENDS_ON)
        
        Returns a set of Node IDs that would be impacted.
        """
        ...


class IParser(Protocol):
    """
    Standard interface for all language parsers.
    """

    def can_parse(self, file_path: Path) -> bool:
        """Return True if this parser handles this file type."""
        ...

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        """
        Parse file content into structured Nodes and Edges.
        
        Must return strict jnkn.core.types objects, not dicts.
        """
        ...