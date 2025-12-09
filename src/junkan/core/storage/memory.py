"""
In-memory storage adapter.

Fast, ephemeral storage for testing and CI pipelines.
"""

from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict

from .base import StorageAdapter
from ..types import Node, Edge, ScanMetadata, NodeType
from ..graph import DependencyGraph


class MemoryStorage(StorageAdapter):
    """
    Ephemeral in-memory storage.
    
    Useful for unit testing, CI pipelines, and development.
    """
    
    def __init__(self):
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str, Edge] = {}
        self._scan_metadata: Dict[str, ScanMetadata] = {}
        self._nodes_by_type: Dict[NodeType, Set[str]] = defaultdict(set)
        self._edges_by_source: Dict[str, Set[str]] = defaultdict(set)
        self._edges_by_target: Dict[str, Set[str]] = defaultdict(set)
    
    def _edge_key(self, source: str, target: str, edge_type: str) -> str:
        """Generate unique key for an edge."""
        return f"{source}|{target}|{edge_type}"
    
    def save_node(self, node: Node) -> None:
        """Persist a single node."""
        self._nodes[node.id] = node
        self._nodes_by_type[node.type].add(node.id)
    
    def save_nodes_batch(self, nodes: List[Node]) -> int:
        """Persist multiple nodes."""
        for node in nodes:
            self.save_node(node)
        return len(nodes)
    
    def load_node(self, node_id: str) -> Optional[Node]:
        """Load a node by ID."""
        return self._nodes.get(node_id)
    
    def load_all_nodes(self) -> List[Node]:
        """Load all nodes."""
        return list(self._nodes.values())
    
    def delete_node(self, node_id: str) -> bool:
        """Delete a node and its edges."""
        if node_id not in self._nodes:
            return False
        
        node = self._nodes[node_id]
        self._nodes_by_type[node.type].discard(node_id)
        del self._nodes[node_id]
        
        for edge_key in list(self._edges_by_source.get(node_id, set())):
            if edge_key in self._edges:
                edge = self._edges[edge_key]
                self._edges_by_target[edge.target_id].discard(edge_key)
                del self._edges[edge_key]
        
        for edge_key in list(self._edges_by_target.get(node_id, set())):
            if edge_key in self._edges:
                edge = self._edges[edge_key]
                self._edges_by_source[edge.source_id].discard(edge_key)
                del self._edges[edge_key]
        
        self._edges_by_source.pop(node_id, None)
        self._edges_by_target.pop(node_id, None)
        
        return True
    
    def delete_nodes_by_file(self, file_path: str) -> int:
        """Delete all nodes from a file."""
        node_ids = [
            node_id for node_id, node in self._nodes.items()
            if node.path == file_path
        ]
        for node_id in node_ids:
            self.delete_node(node_id)
        return len(node_ids)
    
    def save_edge(self, edge: Edge) -> None:
        """Persist a single edge."""
        key = self._edge_key(edge.source_id, edge.target_id, edge.type.value)
        self._edges[key] = edge
        self._edges_by_source[edge.source_id].add(key)
        self._edges_by_target[edge.target_id].add(key)
    
    def save_edges_batch(self, edges: List[Edge]) -> int:
        """Persist multiple edges."""
        for edge in edges:
            self.save_edge(edge)
        return len(edges)
    
    def load_all_edges(self) -> List[Edge]:
        """Load all edges."""
        return list(self._edges.values())
    
    def delete_edges_by_source(self, source_id: str) -> int:
        """Delete all edges from a source."""
        count = 0
        for edge_key in list(self._edges_by_source.get(source_id, set())):
            if edge_key in self._edges:
                edge = self._edges[edge_key]
                self._edges_by_target[edge.target_id].discard(edge_key)
                del self._edges[edge_key]
                count += 1
        self._edges_by_source.pop(source_id, None)
        return count
    
    def load_graph(self) -> DependencyGraph:
        """Hydrate a DependencyGraph."""
        graph = DependencyGraph()
        for node in self._nodes.values():
            graph.add_node(node)
        for edge in self._edges.values():
            graph.add_edge(edge)
        return graph
    
    def query_descendants(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query descendants via BFS."""
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(node_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            
            if max_depth >= 0 and depth >= max_depth:
                continue
            
            for edge_key in self._edges_by_source.get(current, set()):
                edge = self._edges.get(edge_key)
                if edge and edge.target_id not in visited:
                    visited.add(edge.target_id)
                    queue.append((edge.target_id, depth + 1))
        
        return list(visited)
    
    def query_ancestors(self, node_id: str, max_depth: int = -1) -> List[str]:
        """Query ancestors via BFS."""
        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [(node_id, 0)]
        
        while queue:
            current, depth = queue.pop(0)
            
            if max_depth >= 0 and depth >= max_depth:
                continue
            
            for edge_key in self._edges_by_target.get(current, set()):
                edge = self._edges.get(edge_key)
                if edge and edge.source_id not in visited:
                    visited.add(edge.source_id)
                    queue.append((edge.source_id, depth + 1))
        
        return list(visited)
    
    def save_scan_metadata(self, metadata: ScanMetadata) -> None:
        """Save scan metadata."""
        self._scan_metadata[metadata.file_path] = metadata
    
    def get_scan_metadata(self, file_path: str) -> Optional[ScanMetadata]:
        """Get scan metadata for a file."""
        return self._scan_metadata.get(file_path)
    
    def get_all_scan_metadata(self) -> List[ScanMetadata]:
        """Get all scan metadata."""
        return list(self._scan_metadata.values())
    
    def delete_scan_metadata(self, file_path: str) -> bool:
        """Delete scan metadata."""
        if file_path in self._scan_metadata:
            del self._scan_metadata[file_path]
            return True
        return False
    
    def get_schema_version(self) -> int:
        """Memory storage doesn't have schema versions."""
        return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edges),
            "tracked_files": len(self._scan_metadata),
        }
    
    def clear(self) -> None:
        """Clear all data."""
        self._nodes.clear()
        self._edges.clear()
        self._scan_metadata.clear()
        self._nodes_by_type.clear()
        self._edges_by_source.clear()
        self._edges_by_target.clear()
    
    def close(self) -> None:
        """No-op for memory storage."""
        pass