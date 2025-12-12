"""
Graph Implementation backed by rustworkx.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Set

import rustworkx as rx

from .interfaces import IGraph
from .types import Edge, Node, NodeType


@dataclass
class TokenIndex:
    """
    In-memory index for fast fuzzy searching of nodes by tokens.
    """

    _token_map: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))

    def index_node(self, node: Node) -> None:
        if not node.tokens:
            return
        for token in node.tokens:
            self._token_map[token.lower()].add(node.id)

    def find(self, token: str) -> Set[str]:
        return self._token_map.get(token.lower(), set())

    def remove_node(self, node: Node) -> None:
        if not node.tokens:
            return
        for token in node.tokens:
            token_lower = token.lower()
            if token_lower in self._token_map:
                self._token_map[token_lower].discard(node.id)
                if not self._token_map[token_lower]:
                    del self._token_map[token_lower]


class DependencyGraph(IGraph):
    """
    High-performance in-memory dependency graph using rustworkx.
    """

    def __init__(self):
        self._graph = rx.PyDiGraph()
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_node: Dict[int, Node] = {}
        self.token_index = TokenIndex()

    @property
    def node_count(self) -> int:
        return self._graph.num_nodes()

    @property
    def edge_count(self) -> int:
        return self._graph.num_edges()

    def add_node(self, node: Node) -> None:
        if node.id in self._id_to_idx:
            idx = self._id_to_idx[node.id]
            old_node = self._idx_to_node[idx]
            self.token_index.remove_node(old_node)
            self.token_index.index_node(node)
            self._idx_to_node[idx] = node
            self._graph[idx] = node
        else:
            idx = self._graph.add_node(node)
            self._id_to_idx[node.id] = idx
            self._idx_to_node[idx] = node
            self.token_index.index_node(node)

    def add_edge(self, edge: Edge) -> None:
        if edge.source_id not in self._id_to_idx or edge.target_id not in self._id_to_idx:
            return

        src_idx = self._id_to_idx[edge.source_id]
        tgt_idx = self._id_to_idx[edge.target_id]

        # Avoid duplicate edges of same type
        existing = False
        try:
            edges = self._graph.get_all_edge_data(src_idx, tgt_idx)
            for e in edges:
                if e.type == edge.type:
                    existing = True
                    break
        except rx.NoEdgeBetweenNodes:
            pass

        if not existing:
            self._graph.add_edge(src_idx, tgt_idx, edge)

    def get_node(self, node_id: str) -> Node | None:
        idx = self._id_to_idx.get(node_id)
        if idx is not None:
            return self._idx_to_node[idx]
        return None

    def has_node(self, node_id: str) -> bool:
        return node_id in self._id_to_idx

    def has_edge(self, source_id: str, target_id: str) -> bool:
        if source_id not in self._id_to_idx or target_id not in self._id_to_idx:
            return False
        src_idx = self._id_to_idx[source_id]
        tgt_idx = self._id_to_idx[target_id]
        return self._graph.has_edge(src_idx, tgt_idx)

    def remove_node(self, node_id: str) -> None:
        if node_id in self._id_to_idx:
            idx = self._id_to_idx[node_id]
            node = self._idx_to_node[idx]
            self.token_index.remove_node(node)
            self._graph.remove_node(idx)
            del self._id_to_idx[node_id]
            del self._idx_to_node[idx]

    def find_nodes(self, pattern: str) -> List[str]:
        return [nid for nid in self._id_to_idx.keys() if pattern in nid]

    def find_nodes_by_tokens(self, tokens: List[str]) -> List[Node]:
        matched_ids = set()
        for token in tokens:
            matched_ids.update(self.token_index.find(token))
        result = []
        for nid in matched_ids:
            node = self.get_node(nid)
            if node:
                result.append(node)
        return result

    def get_nodes_by_type(self, type_filter: Any) -> List[Node]:
        if not isinstance(type_filter, NodeType):
            try:
                type_filter = NodeType(type_filter)
            except ValueError:
                return []
        return [n for n in self._idx_to_node.values() if n.type == type_filter]

    def get_out_edges(self, node_id: str) -> List[Edge]:
        if node_id not in self._id_to_idx:
            return []
        idx = self._id_to_idx[node_id]
        return [edge_tuple[2] for edge_tuple in self._graph.out_edges(idx)]

    def get_in_edges(self, node_id: str) -> List[Edge]:
        if node_id not in self._id_to_idx:
            return []
        idx = self._id_to_idx[node_id]
        return [edge_tuple[2] for edge_tuple in self._graph.in_edges(idx)]

    def get_edge(self, source_id: str, target_id: str) -> Edge | None:
        if source_id not in self._id_to_idx or target_id not in self._id_to_idx:
            return None
        src_idx = self._id_to_idx[source_id]
        tgt_idx = self._id_to_idx[target_id]
        try:
            edges = self._graph.get_all_edge_data(src_idx, tgt_idx)
            if edges:
                return edges[0]
        except rx.NoEdgeBetweenNodes:
            return None
        return None

    def iter_nodes(self) -> Iterator[Node]:
        return iter(self._idx_to_node.values())

    def iter_edges(self) -> Iterator[Edge]:
        return (edge for edge in self._graph.edges())

    def trace(self, source_id: str, target_id: str) -> List[List[str]]:
        if source_id not in self._id_to_idx or target_id not in self._id_to_idx:
            return []
        src_idx = self._id_to_idx[source_id]
        tgt_idx = self._id_to_idx[target_id]
        try:
            paths_indices = rx.all_simple_paths(self._graph, src_idx, tgt_idx)
            result = []
            for path in paths_indices:
                result.append([self._idx_to_node[i].id for i in path])
            return result
        except Exception:
            return []

    def get_descendants(self, node_id: str, max_depth: int = -1) -> Set[str]:
        if node_id not in self._id_to_idx:
            return set()
        start_idx = self._id_to_idx[node_id]
        descendant_indices = rx.descendants(self._graph, start_idx)
        return {self._idx_to_node[i].id for i in descendant_indices}

    def get_ancestors(self, node_id: str, max_depth: int = -1) -> Set[str]:
        if node_id not in self._id_to_idx:
            return set()
        start_idx = self._id_to_idx[node_id]
        ancestor_indices = rx.ancestors(self._graph, start_idx)
        return {self._idx_to_node[i].id for i in ancestor_indices}

    def get_impacted_nodes(self, source_ids: List[str], max_depth: int = -1) -> Set[str]:
        """
        Calculate impacted nodes using semantic traversal logic.
        Traverses:
        - Outgoing: PROVIDES, WRITES, FLOWS_TO, PROVISIONS
        - Incoming: READS, DEPENDS_ON (Reverse traversal)
        """
        # Define semantic sets using string values for robustness
        FORWARD_TYPES = {"provides", "writes", "flows_to", "provisions", "outputs"}
        REVERSE_TYPES = {"reads", "depends_on", "calls"}

        def normalize_type(val: Any) -> str:
            if hasattr(val, "value"):
                return str(val.value).lower()
            return str(val).lower()

        impacted = set()
        queue = list(source_ids)
        visited = set(source_ids)

        # Track depth if needed (simple BFS level tracking omitted for brevity, using unlimited or basic check)
        # For simplicity in this implementation, we ignore exact max_depth logic beyond a safety break
        # or implement simple level tracking.

        current_level = queue
        depth = 0

        while current_level:
            if max_depth != -1 and depth >= max_depth:
                break

            next_level = []
            for node_id in current_level:
                # 1. Forward Traversal (Downstream)
                out_edges = self.get_out_edges(node_id)
                for edge in out_edges:
                    r_type = normalize_type(edge.type)
                    if r_type in FORWARD_TYPES:
                        neighbor = edge.target_id
                        if neighbor not in visited:
                            visited.add(neighbor)
                            impacted.add(neighbor)
                            next_level.append(neighbor)

                # 2. Reverse Traversal (Upstream Dependencies)
                in_edges = self.get_in_edges(node_id)
                for edge in in_edges:
                    r_type = normalize_type(edge.type)
                    if r_type in REVERSE_TYPES:
                        neighbor = edge.source_id
                        if neighbor not in visited:
                            visited.add(neighbor)
                            impacted.add(neighbor)
                            next_level.append(neighbor)

            current_level = next_level
            depth += 1

        return impacted

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.model_dump() for n in self.iter_nodes()],
            "edges": [e.model_dump() for e in self.iter_edges()],
        }
