"""
Lineage Graph Module.

Provides a lightweight graph implementation for lineage analysis,
with support for upstream/downstream traversal and visualization export.

This can be used standalone or alongside the full DependencyGraph
for quick lineage queries without the full stitching infrastructure.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class LineageGraph:
    """
    Lightweight dependency graph for lineage analysis.
    
    Provides:
    - Node and edge storage
    - Upstream/downstream traversal
    - Cycle detection
    - HTML/DOT export for visualization
    
    Can be loaded from JSON or populated from parser output.
    """
    
    def __init__(self):
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._outgoing: Dict[str, Set[str]] = defaultdict(set)
        self._incoming: Dict[str, Set[str]] = defaultdict(set)
        self._edge_types: Dict[Tuple[str, str], str] = {}
    
    # =========================================================================
    # Node/Edge Management
    # =========================================================================
    
    def add_node(self, node_id: str, **attrs) -> None:
        """Add a node to the graph."""
        self._nodes[node_id] = attrs
    
    def add_edge(self, source: str, target: str, 
                 edge_type: str = "unknown", **attrs) -> None:
        """Add a directed edge to the graph."""
        self._outgoing[source].add(target)
        self._incoming[target].add(source)
        self._edge_types[(source, target)] = edge_type
    
    def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get a node by ID."""
        return self._nodes.get(node_id)
    
    def has_node(self, node_id: str) -> bool:
        """Check if a node exists."""
        return node_id in self._nodes
    
    # =========================================================================
    # Loading
    # =========================================================================
    
    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """
        Load graph from a dictionary.
        
        Expected format:
        {
            "nodes": [{"id": "...", "name": "...", ...}, ...],
            "edges": [{"source": "...", "target": "...", "type": "..."}, ...]
        }
        """
        for node in data.get("nodes", []):
            node_id = node.get("id", "")
            if node_id:
                self.add_node(node_id, **node)
        
        for edge in data.get("edges", []):
            source = edge.get("source_id") or edge.get("source", "")
            target = edge.get("target_id") or edge.get("target", "")
            edge_type = str(edge.get("type", "unknown"))
            if source and target:
                self.add_edge(source, target, edge_type)
    
    def load_from_json(self, json_str: str) -> None:
        """Load graph from JSON string."""
        data = json.loads(json_str)
        self.load_from_dict(data)
    
    # =========================================================================
    # Traversal
    # =========================================================================
    
    def downstream(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """
        Find all nodes downstream of the given node.
        
        Downstream = nodes that would be affected by changes to this node.
        
        For data nodes: code that READS from this data
        For code nodes: data that this code WRITES to
        """
        visited: Set[str] = set()
        to_visit: List[Tuple[str, int]] = [(node_id, 0)]
        
        while to_visit:
            current, depth = to_visit.pop(0)
            
            if current in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue
            
            visited.add(current)
            
            # Find consumers (things that read from current)
            for source in self._incoming.get(current, set()):
                edge_type = self._edge_types.get((source, current), "").lower()
                if edge_type == "reads":
                    if source not in visited:
                        to_visit.append((source, depth + 1))
            
            # Find outputs (things current writes to)
            for target in self._outgoing.get(current, set()):
                edge_type = self._edge_types.get((current, target), "").lower()
                if edge_type in ("writes", "depends_on"):
                    if target not in visited:
                        to_visit.append((target, depth + 1))
        
        visited.discard(node_id)
        return visited
    
    def upstream(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """
        Find all nodes upstream of the given node.
        
        Upstream = source nodes that feed into this node.
        
        For code nodes: data that this code READS from
        For data nodes: code that WRITES to this data
        """
        visited: Set[str] = set()
        to_visit: List[Tuple[str, int]] = [(node_id, 0)]
        
        while to_visit:
            current, depth = to_visit.pop(0)
            
            if current in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue
            
            visited.add(current)
            
            # Find sources (things current reads from)
            for target in self._outgoing.get(current, set()):
                edge_type = self._edge_types.get((current, target), "").lower()
                if edge_type == "reads":
                    if target not in visited:
                        to_visit.append((target, depth + 1))
            
            # Find producers (things that write to current)
            for source in self._incoming.get(current, set()):
                edge_type = self._edge_types.get((source, current), "").lower()
                if edge_type == "writes":
                    if source not in visited:
                        to_visit.append((source, depth + 1))
        
        visited.discard(node_id)
        return visited
    
    def trace(self, source_id: str, target_id: str, 
              max_length: int = 20) -> List[List[str]]:
        """
        Find all paths between two nodes.
        
        Returns list of paths (each path is a list of node IDs).
        """
        if source_id not in self._nodes or target_id not in self._nodes:
            return []
        
        paths: List[List[str]] = []
        queue: List[Tuple[str, List[str]]] = [(source_id, [source_id])]
        
        while queue:
            current, path = queue.pop(0)
            
            if current == target_id:
                paths.append(path)
                continue
            
            if len(path) >= max_length:
                continue
            
            # Try outgoing edges
            for neighbor in self._outgoing.get(current, set()):
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))
            
            # Try incoming edges (bidirectional search)
            for neighbor in self._incoming.get(current, set()):
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))
        
        return paths
    
    # =========================================================================
    # Search
    # =========================================================================
    
    def find_nodes(self, pattern: str) -> List[str]:
        """
        Find nodes matching a pattern (case-insensitive substring).
        
        Searches both node IDs and names.
        """
        pattern_lower = pattern.lower()
        results = []
        
        for node_id, attrs in self._nodes.items():
            if pattern_lower in node_id.lower():
                results.append(node_id)
            elif pattern_lower in attrs.get("name", "").lower():
                results.append(node_id)
        
        return results
    
    # =========================================================================
    # Analysis
    # =========================================================================
    
    def find_orphans(self) -> List[str]:
        """Find nodes with no connections."""
        orphans = []
        for node_id in self._nodes:
            if not self._outgoing.get(node_id) and not self._incoming.get(node_id):
                orphans.append(node_id)
        return orphans
    
    def find_cycles(self) -> List[List[str]]:
        """Find cycles in the graph using DFS."""
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        
        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self._outgoing.get(node, set()):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])
            
            path.pop()
            rec_stack.remove(node)
        
        for node in self._nodes:
            if node not in visited:
                dfs(node, [])
        
        return cycles
    
    # =========================================================================
    # Statistics
    # =========================================================================
    
    def stats(self) -> Dict[str, Any]:
        """Get graph statistics."""
        nodes_by_type: Dict[str, int] = defaultdict(int)
        
        for node_id in self._nodes:
            if node_id.startswith("data:"):
                nodes_by_type["data"] += 1
            elif node_id.startswith(("file:", "job:")):
                nodes_by_type["code"] += 1
            elif node_id.startswith("env:"):
                nodes_by_type["config"] += 1
            elif node_id.startswith("infra:"):
                nodes_by_type["infra"] += 1
            else:
                nodes_by_type["other"] += 1
        
        edges_by_type: Dict[str, int] = defaultdict(int)
        for (_, _), edge_type in self._edge_types.items():
            edges_by_type[edge_type] += 1
        
        return {
            "total_nodes": len(self._nodes),
            "total_edges": len(self._edge_types),
            "nodes_by_type": dict(nodes_by_type),
            "edges_by_type": dict(edges_by_type),
            "orphans": len(self.find_orphans()),
        }
    
    # =========================================================================
    # Export
    # =========================================================================
    
    def to_dict(self) -> Dict[str, Any]:
        """Export graph as dictionary."""
        return {
            "nodes": [
                {"id": node_id, **attrs}
                for node_id, attrs in self._nodes.items()
            ],
            "edges": [
                {"source": src, "target": tgt, "type": edge_type}
                for (src, tgt), edge_type in self._edge_types.items()
            ],
            "stats": self.stats(),
        }
    
    def to_json(self, indent: int = 2) -> str:
        """Export graph as JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    def to_dot(self) -> str:
        """Export graph as DOT format for Graphviz."""
        lines = ["digraph lineage {"]
        lines.append("  rankdir=LR;")
        lines.append("  node [shape=box];")
        lines.append("")
        
        colors = {
            "data": "#4CAF50",
            "code": "#2196F3",
            "config": "#FF9800",
            "infra": "#9C27B0",
        }
        
        for node_id, attrs in self._nodes.items():
            # Determine color
            if node_id.startswith("data:"):
                color = colors["data"]
            elif node_id.startswith(("file:", "job:")):
                color = colors["code"]
            elif node_id.startswith("env:"):
                color = colors["config"]
            elif node_id.startswith("infra:"):
                color = colors["infra"]
            else:
                color = "#757575"
            
            name = attrs.get("name", node_id)
            label = name.split(".")[-1] if "." in name else name.split("/")[-1]
            label = label.replace('"', '\\"')
            
            lines.append(f'  "{node_id}" [label="{label}", fillcolor="{color}", '
                        f'style=filled, fontcolor=white];')
        
        lines.append("")
        
        for (src, tgt), edge_type in self._edge_types.items():
            style = "dashed" if edge_type == "reads" else "solid"
            lines.append(f'  "{src}" -> "{tgt}" [style={style}];')
        
        lines.append("}")
        return "\n".join(lines)
    
    def export_html(self, output_path: Path) -> None:
        """Export interactive HTML visualization using vis.js."""
        from .visualize import generate_html
        
        html = generate_html(self)
        output_path.write_text(html)