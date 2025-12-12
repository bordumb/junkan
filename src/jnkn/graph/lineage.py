"""
Lineage Graph Module.

Provides a lightweight, traversable graph structure optimized for lineage analysis,
visualization, and export.

This graph structure is distinct from the core `DependencyGraph` in that it focuses
on directional flow and pathfinding (upstream/downstream) rather than just storage.
It supports serialization to JSON and DOT formats, as well as HTML visualization export.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


class LineageGraph:
    """
    Lightweight dependency graph for lineage analysis.

    Supports directed graph operations including upstream/downstream traversal,
    cycle detection, and orphan identification. Can be hydrated from JSON or dictionaries.

    Attributes:
        _nodes (Dict[str, Dict[str, Any]]): Internal storage of node attributes keyed by ID.
        _outgoing (Dict[str, Set[str]]): Adjacency list for outgoing edges.
        _incoming (Dict[str, Set[str]]): Adjacency list for incoming edges.
        _edge_types (Dict[Tuple[str, str], str]): Storage for edge types keyed by (source, target).
    """

    def __init__(self):
        """Initialize an empty LineageGraph."""
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._outgoing: Dict[str, Set[str]] = defaultdict(set)
        self._incoming: Dict[str, Set[str]] = defaultdict(set)
        self._edge_types: Dict[Tuple[str, str], str] = {}

    def add_node(self, node_id: str, **attrs) -> None:
        """
        Add a node to the graph.

        Args:
            node_id (str): Unique identifier for the node.
            **attrs: Arbitrary attributes (metadata) to store with the node.
        """
        self._nodes[node_id] = attrs

    def add_edge(self, source: str, target: str, edge_type: str = "unknown", **attrs) -> None:
        """
        Add a directed edge to the graph.

        Args:
            source (str): Source node ID.
            target (str): Target node ID.
            edge_type (str): Type of relationship (e.g., 'reads', 'writes', 'provides').
            **attrs: Additional metadata for the edge.
        """
        self._outgoing[source].add(target)
        self._incoming[target].add(source)
        # Normalize edge type to lowercase for consistent traversal checks
        self._edge_types[(source, target)] = edge_type.lower()

    def get_node(self, node_id: str) -> Dict[str, Any] | None:
        """
        Retrieve node attributes by ID.

        Args:
            node_id (str): The ID to look up.

        Returns:
            Dict[str, Any] | None: Node attributes or None if not found.
        """
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        """
        Check if a node exists in the graph.

        Args:
            node_id (str): The ID to check.

        Returns:
            bool: True if the node exists.
        """
        return node_id in self._nodes

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        """
        Hydrate the graph from a dictionary structure.

        Args:
            data (Dict[str, Any]): Dictionary containing 'nodes' and 'edges' lists.
        """
        for node in data.get("nodes", []):
            node_id = node.get("id", "")
            if node_id:
                # Filter out None values to keep dict clean
                attrs = {k: v for k, v in node.items() if k != "id" and v is not None}
                self.add_node(node_id, **attrs)

        for edge in data.get("edges", []):
            source = edge.get("source_id") or edge.get("source", "")
            target = edge.get("target_id") or edge.get("target", "")
            edge_type = str(edge.get("type", "unknown"))
            if source and target:
                self.add_edge(source, target, edge_type)

    def load_from_json(self, json_str: str) -> None:
        """
        Hydrate the graph from a JSON string.

        Args:
            json_str (str): Valid JSON string representing the graph.
        """
        data = json.loads(json_str)
        self.load_from_dict(data)

    def downstream(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """
        Find all nodes downstream of the given node (Blast Radius).

        This algorithm determines impact propagation based on edge semantics.
        Impact flows:
        1. FORWARD along 'push' edges (writes, provides, configures).
           (e.g., Infra PROVIDES EnvVar -> Change Infra implies EnvVar changes).
        2. BACKWARD against 'pull' edges (reads, depends_on, imports).
           (e.g., Code READS EnvVar -> Change EnvVar implies Code breaks).

        Args:
            node_id (str): Starting node ID.
            max_depth (int): Maximum depth to traverse. -1 for unlimited.

        Returns:
            Set[str]: A set of all downstream/impacted node IDs.
        """
        visited: Set[str] = set()
        to_visit: List[Tuple[str, int]] = [(node_id, 0)]

        # Edges where impact flows Source -> Target (Forward traversal)
        forward_impact_types = {
            "writes",
            "provides",
            "provisions",
            "configures",
            "transforms",
            "triggers",
            "calls",
        }

        # Edges where impact flows Target -> Source (Reverse traversal)
        reverse_impact_types = {"reads", "imports", "depends_on", "consumes", "requires"}

        while to_visit:
            current, depth = to_visit.pop(0)

            if current in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue

            visited.add(current)

            # 1. Forward Traversal: Check outgoing edges
            # If current node PROVIDES target, then target is impacted.
            for target in self._outgoing.get(current, set()):
                edge_type = self._edge_types.get((current, target), "unknown")
                if edge_type in forward_impact_types:
                    if target not in visited:
                        to_visit.append((target, depth + 1))

            # 2. Reverse Traversal: Check incoming edges
            # If source READS current node, then source is impacted.
            for source in self._incoming.get(current, set()):
                edge_type = self._edge_types.get((source, current), "unknown")
                if edge_type in reverse_impact_types:
                    if source not in visited:
                        to_visit.append((source, depth + 1))

        # Remove the starting node from the result set
        visited.discard(node_id)
        return visited

    def upstream(self, node_id: str, max_depth: int = -1) -> Set[str]:
        """
        Find all nodes upstream of the given node (Root Cause Analysis).

        Traverses the graph backwards against impact flow to find dependencies.

        Args:
            node_id (str): Starting node ID.
            max_depth (int): Maximum depth to traverse. -1 for unlimited.

        Returns:
            Set[str]: A set of all upstream node IDs.
        """
        visited: Set[str] = set()
        to_visit: List[Tuple[str, int]] = [(node_id, 0)]

        # Edges where dependency is Source -> Target
        # (e.g. Infra PROVIDES EnvVar -> EnvVar depends on Infra)
        dependency_provider_types = {
            "writes",
            "provides",
            "provisions",
            "configures",
            "transforms",
            "triggers",
            "calls",
        }

        # Edges where dependency is Target -> Source
        # (e.g. Code READS EnvVar -> Code depends on EnvVar)
        dependency_consumer_types = {"reads", "imports", "depends_on", "consumes", "requires"}

        while to_visit:
            current, depth = to_visit.pop(0)

            if current in visited:
                continue
            if max_depth >= 0 and depth > max_depth:
                continue

            visited.add(current)

            # 1. Check incoming edges (Who provides for me?)
            for source in self._incoming.get(current, set()):
                edge_type = self._edge_types.get((source, current), "unknown")
                if edge_type in dependency_provider_types:
                    if source not in visited:
                        to_visit.append((source, depth + 1))

            # 2. Check outgoing edges (Who do I read from?)
            for target in self._outgoing.get(current, set()):
                edge_type = self._edge_types.get((current, target), "unknown")
                if edge_type in dependency_consumer_types:
                    if target not in visited:
                        to_visit.append((target, depth + 1))

        visited.discard(node_id)
        return visited

    def trace(self, source_id: str, target_id: str, max_length: int = 20) -> List[List[str]]:
        """
        Find all directed paths between two nodes.

        Args:
            source_id (str): Start node ID.
            target_id (str): End node ID.
            max_length (int): Maximum path length to avoid infinite loops in cycles.

        Returns:
            List[List[str]]: A list of paths, where each path is a list of node IDs.
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

            for neighbor in self._outgoing.get(current, set()):
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))

        return paths

    def find_nodes(self, pattern: str) -> List[str]:
        """
        Find nodes matching a substring pattern.

        Searches both node IDs and 'name' attributes.

        Args:
            pattern (str): The search string (case-insensitive).

        Returns:
            List[str]: List of matching node IDs.
        """
        pattern_lower = pattern.lower()
        results = []

        for node_id, attrs in self._nodes.items():
            if pattern_lower in node_id.lower():
                results.append(node_id)
            elif pattern_lower in attrs.get("name", "").lower():
                results.append(node_id)

        return results

    def find_orphans(self) -> List[str]:
        """
        Identify nodes with no connections (orphan nodes).

        Returns:
            List[str]: List of orphan node IDs.
        """
        orphans = []
        for node_id in self._nodes:
            if not self._outgoing.get(node_id) and not self._incoming.get(node_id):
                orphans.append(node_id)
        return orphans

    def find_cycles(self) -> List[List[str]]:
        """
        Detect circular dependencies in the graph.

        Returns:
            List[List[str]]: A list of cycles detected, where each cycle is a list of node IDs.
        """
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
                    # Cycle detected
                    try:
                        cycle_start = path.index(neighbor)
                        cycles.append(path[cycle_start:] + [neighbor])
                    except ValueError:
                        pass

            path.pop()
            rec_stack.remove(node)

        for node in self._nodes:
            if node not in visited:
                dfs(node, [])

        return cycles

    def stats(self) -> Dict[str, Any]:
        """
        Generate statistical summary of the graph.

        Returns:
            Dict[str, Any]: A dictionary containing counts of nodes, edges, types, and orphans.
        """
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
            elif node_id.startswith("k8s:"):
                nodes_by_type["k8s"] += 1
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

    def to_dict(self) -> Dict[str, Any]:
        """
        Export graph to dictionary format suitable for JSON serialization.

        Returns:
            Dict[str, Any]: The graph data structure.
        """
        return {
            "nodes": [{"id": nid, **attrs} for nid, attrs in self._nodes.items()],
            "edges": [
                {"source": s, "target": t, "type": ty} for (s, t), ty in self._edge_types.items()
            ],
            "stats": self.stats(),
        }

    def to_json(self, indent: int = 2) -> str:
        """
        Export graph to JSON string.

        Args:
            indent (int): Indentation level for pretty-printing.

        Returns:
            str: JSON string.
        """
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def to_dot(self) -> str:
        """
        Export graph to Graphviz DOT format.

        Returns:
            str: DOT formatted string.
        """
        lines = ["digraph lineage {", "  rankdir=LR;", "  node [shape=box];", ""]
        colors = {"data": "#4CAF50", "code": "#2196F3", "config": "#FF9800", "infra": "#9C27B0"}

        for node_id, attrs in self._nodes.items():
            color = "#757575"
            if node_id.startswith("data:"):
                color = colors["data"]
            elif node_id.startswith(("file:", "job:")):
                color = colors["code"]
            elif node_id.startswith("env:"):
                color = colors["config"]
            elif node_id.startswith("infra:"):
                color = colors["infra"]

            name = attrs.get("name", node_id)
            label = name.split(".")[-1] if "." in name else name.split("/")[-1]
            lines.append(
                f'  "{node_id}" [label="{label}", fillcolor="{color}", style=filled, fontcolor=white];'
            )

        lines.append("")
        for (src, tgt), edge_type in self._edge_types.items():
            style = "dashed" if edge_type == "reads" else "solid"
            lines.append(f'  "{src}" -> "{tgt}" [style={style}];')

        lines.append("}")
        return "\n".join(lines)

    def export_html(self, output_path: Path) -> None:
        """
        Export interactive HTML visualization using Vis.js.

        Args:
            output_path (Path): Destination path for the HTML file.
        """
        from .visualize import generate_html

        html = generate_html(self)
        output_path.write_text(html)
