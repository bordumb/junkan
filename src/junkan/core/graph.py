"""
Dependency Graph implementation.

This module provides a type-safe wrapper around NetworkX that:
- Manages nodes and edges with proper typing
- Supports efficient traversal operations
- Maintains an inverted index for fast node lookups by type and tokens
- Provides graph statistics and export capabilities
"""

import networkx as nx
from typing import List, Set, Dict, Optional, Iterator, Tuple, Any
from collections import defaultdict
from .types import Node, Edge, NodeType, RelationshipType


class TokenIndex:
    """
    Inverted index mapping tokens to node IDs.
    
    Enables O(1) lookup of nodes containing specific tokens,
    critical for efficient stitching operations (O(n) vs O(n*m)).
    """
    
    def __init__(self):
        self._token_to_nodes: Dict[str, Set[str]] = defaultdict(set)
        self._node_to_tokens: Dict[str, Set[str]] = defaultdict(set)
    
    def add(self, node_id: str, tokens: List[str]) -> None:
        """Index a node by its tokens."""
        for token in tokens:
            self._token_to_nodes[token].add(node_id)
            self._node_to_tokens[node_id].add(token)
    
    def remove(self, node_id: str) -> None:
        """Remove a node from the index."""
        if node_id in self._node_to_tokens:
            for token in self._node_to_tokens[node_id]:
                self._token_to_nodes[token].discard(node_id)
            del self._node_to_tokens[node_id]
    
    def find_by_token(self, token: str) -> Set[str]:
        """Find all node IDs containing a specific token."""
        return self._token_to_nodes.get(token, set()).copy()
    
    def find_by_any_token(self, tokens: List[str]) -> Set[str]:
        """Find all node IDs containing any of the given tokens."""
        result = set()
        for token in tokens:
            result.update(self._token_to_nodes.get(token, set()))
        return result
    
    def find_by_all_tokens(self, tokens: List[str]) -> Set[str]:
        """Find all node IDs containing all of the given tokens."""
        if not tokens:
            return set()
        result = self._token_to_nodes.get(tokens[0], set()).copy()
        for token in tokens[1:]:
            result &= self._token_to_nodes.get(token, set())
        return result
    
    def get_tokens(self, node_id: str) -> Set[str]:
        """Get all tokens for a node."""
        return self._node_to_tokens.get(node_id, set()).copy()
    
    @property
    def token_count(self) -> int:
        """Number of unique tokens indexed."""
        return len(self._token_to_nodes)


class DependencyGraph:
    """
    Type-safe wrapper around NetworkX.
    
    Provides:
    - Node and edge management with type safety
    - Efficient lookups by node type via secondary index
    - Token-based inverted index for fast stitching
    - Graph traversal operations (descendants, ancestors)
    - Statistics and export capabilities
    """
    
    def __init__(self):
        self._graph = nx.DiGraph()
        self._nodes_by_type: Dict[NodeType, Set[str]] = defaultdict(set)
        self._token_index = TokenIndex()

    def add_node(self, node: Node) -> None:
        """
        Add a node to the graph.
        
        Also updates secondary indices for efficient lookups.
        """
        self._graph.add_node(node.id, data=node)
        self._nodes_by_type[node.type].add(node.id)
        if node.tokens:
            self._token_index.add(node.id, node.tokens)

    def remove_node(self, node_id: str) -> None:
        """
        Remove a node and all its edges from the graph.
        
        Also cleans up secondary indices.
        """
        if node_id not in self._graph:
            return
        
        node_data = self._graph.nodes[node_id].get("data")
        if node_data:
            self._nodes_by_type[node_data.type].discard(node_id)
        
        self._token_index.remove(node_id)
        self._graph.remove_node(node_id)

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge between two nodes."""
        self._graph.add_edge(
            edge.source_id,
            edge.target_id,
            data=edge
        )

    def remove_edges_from_source(self, source_id: str) -> int:
        """
        Remove all edges originating from a source node.
        
        Used during incremental re-scanning to clear stale edges.
        """
        if source_id not in self._graph:
            return 0
        
        edges_to_remove = list(self._graph.out_edges(source_id))
        self._graph.remove_edges_from(edges_to_remove)
        return len(edges_to_remove)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Retrieve a node by ID."""
        if node_id not in self._graph:
            return None
        return self._graph.nodes[node_id].get("data")

    def get_edge(self, source_id: str, target_id: str) -> Optional[Edge]:
        """Retrieve an edge by source and target IDs."""
        if not self._graph.has_edge(source_id, target_id):
            return None
        return self._graph.edges[source_id, target_id].get("data")

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists in the graph."""
        return node_id in self._graph

    def has_edge(self, source_id: str, target_id: str) -> bool:
        """Check if an edge exists between two nodes."""
        return self._graph.has_edge(source_id, target_id)

    def get_nodes_by_type(self, node_type: NodeType) -> List[Node]:
        """
        Get all nodes of a specific type.
        
        Uses secondary index for O(1) lookup of node IDs.
        """
        nodes = []
        for node_id in self._nodes_by_type.get(node_type, set()):
            node = self.get_node(node_id)
            if node:
                nodes.append(node)
        return nodes

    def get_node_ids_by_type(self, node_type: NodeType) -> Set[str]:
        """Get all node IDs of a specific type."""
        return self._nodes_by_type.get(node_type, set()).copy()

    def find_nodes_by_tokens(
        self, tokens: List[str], match_all: bool = False
    ) -> List[Node]:
        """
        Find nodes matching given tokens using inverted index.
        
        Args:
            tokens: List of tokens to match
            match_all: If True, nodes must contain all tokens
        """
        if match_all:
            node_ids = self._token_index.find_by_all_tokens(tokens)
        else:
            node_ids = self._token_index.find_by_any_token(tokens)
        
        return [self.get_node(nid) for nid in node_ids if self.get_node(nid)]

    def get_descendants(self, node_id: str) -> Set[str]:
        """Get all nodes reachable from the given node."""
        if node_id not in self._graph:
            return set()
        return nx.descendants(self._graph, node_id)

    def get_ancestors(self, node_id: str) -> Set[str]:
        """Get all nodes that can reach the given node."""
        if node_id not in self._graph:
            return set()
        return nx.ancestors(self._graph, node_id)

    def get_direct_dependencies(self, node_id: str) -> List[Tuple[str, Edge]]:
        """Get direct outgoing edges from a node."""
        if node_id not in self._graph:
            return []
        
        result = []
        for _, target_id, data in self._graph.out_edges(node_id, data=True):
            edge = data.get("data")
            if edge:
                result.append((target_id, edge))
        return result

    def get_direct_dependents(self, node_id: str) -> List[Tuple[str, Edge]]:
        """Get direct incoming edges to a node."""
        if node_id not in self._graph:
            return []
        
        result = []
        for source_id, _, data in self._graph.in_edges(node_id, data=True):
            edge = data.get("data")
            if edge:
                result.append((source_id, edge))
        return result

    def iter_nodes(self) -> Iterator[Node]:
        """Iterate over all nodes in the graph."""
        for node_id in self._graph.nodes():
            node = self.get_node(node_id)
            if node:
                yield node

    def iter_edges(self) -> Iterator[Edge]:
        """Iterate over all edges in the graph."""
        for source_id, target_id, data in self._graph.edges(data=True):
            edge = data.get("data")
            if edge:
                yield edge

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the graph."""
        return self._graph.number_of_nodes()

    @property
    def edge_count(self) -> int:
        """Return the number of edges in the graph."""
        return self._graph.number_of_edges()

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive graph statistics."""
        node_counts = {
            node_type.value: len(self._nodes_by_type.get(node_type, set()))
            for node_type in NodeType
        }
        
        edge_counts: Dict[str, int] = defaultdict(int)
        for edge in self.iter_edges():
            edge_counts[edge.type.value] += 1
        
        return {
            "total_nodes": self.node_count,
            "total_edges": self.edge_count,
            "nodes_by_type": node_counts,
            "edges_by_type": dict(edge_counts),
            "indexed_tokens": self._token_index.token_count,
        }

    def clear(self) -> None:
        """Remove all nodes and edges from the graph."""
        self._graph.clear()
        self._nodes_by_type.clear()
        self._token_index = TokenIndex()

    def to_dict(self) -> Dict[str, Any]:
        """Export graph to dictionary format."""
        return {
            "nodes": [node.model_dump() for node in self.iter_nodes()],
            "edges": [edge.model_dump() for edge in self.iter_edges()],
            "stats": self.get_stats(),
        }