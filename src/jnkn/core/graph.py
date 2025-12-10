"""
Dependency Graph implementation backed by rustworkx.

This module replaces the NetworkX backend with rustworkx for significant
performance gains (10-100x) in graph traversal and analysis.

It manages:
- The bimap between string Node IDs and rustworkx integer indices.
- Type-safe Node and Edge data storage.
- Efficient token-based lookups.
- Semantic impact analysis (traversing against 'read' edges).
"""

from collections import defaultdict, deque
from typing import Any, Dict, Iterator, List, Optional, Set

import rustworkx as rx

from .types import Edge, Node, NodeType


class TokenIndex:
    """
    Inverted index mapping tokens to node IDs.
    
    Enables O(1) lookup of nodes containing specific tokens,
    critical for efficient stitching operations.
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
                if not self._token_to_nodes[token]:
                    del self._token_to_nodes[token]
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
        
        sorted_tokens = sorted(tokens, key=lambda t: len(self._token_to_nodes.get(t, set())))
        
        result = self._token_to_nodes.get(sorted_tokens[0], set()).copy()
        if not result:
            return set()
            
        for token in sorted_tokens[1:]:
            result &= self._token_to_nodes.get(token, set())
            if not result:
                break
        return result

    @property
    def token_count(self) -> int:
        """Number of unique tokens indexed."""
        return len(self._token_to_nodes)


class DependencyGraph:
    """
    High-performance dependency graph using rustworkx.

    Features:
    - O(1) node lookup via ID-to-Index bimap
    - Fast C++ / Rust backend for traversals
    - Semantic impact analysis
    """

    def __init__(self):
        self._graph = rx.PyDiGraph(multigraph=True)
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_id: Dict[int, str] = {}
        self._nodes_by_type: Dict[NodeType, Set[str]] = defaultdict(set)
        self._token_index = TokenIndex()

    def add_node(self, node: Node) -> None:
        """Add or update a node in the graph."""
        if node.id in self._id_to_idx:
            idx = self._id_to_idx[node.id]
            self._graph[idx] = node
        else:
            idx = self._graph.add_node(node)
            self._id_to_idx[node.id] = idx
            self._idx_to_id[idx] = node.id
        
        self._nodes_by_type[node.type].add(node.id)
        if node.tokens:
            self._token_index.add(node.id, node.tokens)

    def remove_node(self, node_id: str) -> None:
        """Remove a node and all connected edges."""
        if node_id not in self._id_to_idx:
            return

        idx = self._id_to_idx[node_id]
        node: Node = self._graph[idx]
        self._nodes_by_type[node.type].discard(node_id)
        self._token_index.remove(node_id)
        
        self._graph.remove_node(idx)
        
        del self._id_to_idx[node_id]
        del self._idx_to_id[idx]

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge between two nodes."""
        if edge.source_id not in self._id_to_idx or edge.target_id not in self._id_to_idx:
            return

        u_idx = self._id_to_idx[edge.source_id]
        v_idx = self._id_to_idx[edge.target_id]
        self._graph.add_edge(u_idx, v_idx, edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Retrieve a node by ID."""
        idx = self._id_to_idx.get(node_id)
        if idx is None:
            return None
        return self._graph[idx]

    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return node_id in self._id_to_idx

    def has_edge(self, source_id: str, target_id: str) -> bool:
        """Check if an edge exists between two nodes."""
        if source_id not in self._id_to_idx or target_id not in self._id_to_idx:
            return False
        
        u = self._id_to_idx[source_id]
        v = self._id_to_idx[target_id]
        return self._graph.has_edge(u, v)

    def get_nodes_by_type(self, node_type: NodeType) -> List[Node]:
        """Get all nodes of a specific type."""
        nodes = []
        for node_id in self._nodes_by_type.get(node_type, set()):
            node = self.get_node(node_id)
            if node:
                nodes.append(node)
        return nodes

    def find_nodes(self, pattern: str) -> List[str]:
        """
        Find nodes matching a substring pattern.
        
        Searches IDs and Name attributes.
        """
        results = []
        pattern_lower = pattern.lower()
        for node in self.iter_nodes():
            if pattern_lower in node.id.lower() or pattern_lower in node.name.lower():
                results.append(node.id)
        return results

    def find_nodes_by_tokens(self, tokens: List[str], match_all: bool = False) -> List[Node]:
        """Find nodes matching tokens using the inverted index."""
        if match_all:
            node_ids = self._token_index.find_by_all_tokens(tokens)
        else:
            node_ids = self._token_index.find_by_any_token(tokens)
            
        return [self.get_node(nid) for nid in node_ids if self.get_node(nid)]

    def get_descendants(self, node_id: str) -> Set[str]:
        """Get all node IDs strictly reachable (downstream edges)."""
        if node_id not in self._id_to_idx:
            return set()
        start_idx = self._id_to_idx[node_id]
        descendant_indices = rx.descendants(self._graph, start_idx)
        return {self._idx_to_id[idx] for idx in descendant_indices}

    def get_ancestors(self, node_id: str) -> Set[str]:
        """Get all node IDs strictly reaching (upstream edges)."""
        if node_id not in self._id_to_idx:
            return set()
        start_idx = self._id_to_idx[node_id]
        ancestor_indices = rx.ancestors(self._graph, start_idx)
        return {self._idx_to_id[idx] for idx in ancestor_indices}

    def get_impacted_nodes(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """
        Get nodes semantically impacted by a change to node_id.
        
        This logic accounts for edge direction semantics:
        - Traverses OUTGOING edges for 'push' relationships (WRITES, PROVIDES)
        - Traverses INCOMING edges for 'pull' relationships (READS, IMPORTS)
        
        Example:
            File -> READS -> EnvVar
            Change to EnvVar impacts File (Incoming 'READS' edge).
        """
        if node_id not in self._id_to_idx:
            return set()

        start_idx = self._id_to_idx[node_id]
        visited_indices = set()
        queue = deque([(start_idx, 0)])
        
        # Edges where impact flows Target -> Source (Reverse traversal)
        reverse_impact_types = {
            "reads", "imports", "depends_on", "consumes", "requires"
        }
        
        # Edges where impact flows Source -> Target (Forward traversal)
        forward_impact_types = {
            "writes", "provides", "provisions", "configures", 
            "transforms", "triggers", "calls"
        }

        while queue:
            current_idx, depth = queue.popleft()
            
            if current_idx in visited_indices:
                continue
            
            if max_depth >= 0 and depth > max_depth:
                continue
                
            visited_indices.add(current_idx)
            
            # 1. Check Incoming Edges (Reverse Impact)
            # If Source READS Current, then Source is impacted by Current
            for source_idx, _, edge_data in self._graph.in_edges(current_idx):
                if edge_data.type.value in reverse_impact_types:
                    if source_idx not in visited_indices:
                        queue.append((source_idx, depth + 1))

            # 2. Check Outgoing Edges (Forward Impact)
            # If Current WRITES Target, then Target is impacted by Current
            for _, target_idx, edge_data in self._graph.out_edges(current_idx):
                if edge_data.type.value in forward_impact_types:
                    if target_idx not in visited_indices:
                        queue.append((target_idx, depth + 1))

        # Remove self
        visited_indices.discard(start_idx)
        return {self._idx_to_id[idx] for idx in visited_indices}

    def trace(self, source_id: str, target_id: str) -> List[List[str]]:
        """
        Find paths between source and target.
        
        This finds paths in the raw graph (Graph Direction).
        Usually shows dependency flow (Source READS Target).
        """
        if source_id not in self._id_to_idx or target_id not in self._id_to_idx:
            return []

        src_idx = self._id_to_idx[source_id]
        tgt_idx = self._id_to_idx[target_id]

        # rustworkx all_simple_paths
        try:
            # Limit depth to avoid explosion in large graphs
            paths_indices = rx.all_simple_paths(self._graph, src_idx, tgt_idx, cutoff=10)
            
            # Convert indices back to IDs
            return [
                [self._idx_to_id[idx] for idx in path]
                for path in paths_indices
            ]
        except Exception:
            return []

    def iter_nodes(self) -> Iterator[Node]:
        return iter(self._graph.nodes())

    def iter_edges(self) -> Iterator[Edge]:
        return iter(self._graph.edges())

    @property
    def node_count(self) -> int:
        return self._graph.num_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.num_edges()

    def get_stats(self) -> Dict[str, Any]:
        node_counts = {
            node_type.value: len(ids)
            for node_type, ids in self._nodes_by_type.items()
        }
        edge_counts: Dict[str, int] = defaultdict(int)
        for edge in self.iter_edges():
            edge_counts[edge.type.value] += 1

        # Check connectivity
        try:
            orphans = len([n for n in self._graph.node_indices() 
                          if self._graph.in_degree(n) == 0 and self._graph.out_degree(n) == 0])
        except:
            orphans = 0

        return {
            "total_nodes": self.node_count,
            "total_edges": self.edge_count,
            "nodes_by_type": node_counts,
            "edges_by_type": dict(edge_counts),
            "indexed_tokens": self._token_index.token_count,
            "backend": "rustworkx",
            "orphans": orphans
        }

    def clear(self) -> None:
        self._graph = rx.PyDiGraph(multigraph=True)
        self._id_to_idx.clear()
        self._idx_to_id.clear()
        self._nodes_by_type.clear()
        self._token_index = TokenIndex()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [node.model_dump() for node in self.iter_nodes()],
            "edges": [edge.model_dump() for edge in self.iter_edges()],
            "stats": self.get_stats(),
        }
