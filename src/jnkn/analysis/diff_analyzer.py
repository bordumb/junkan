"""
Diff Analyzer - Analyze semantic changes between two dependency graphs.

Identifies:
1. Added/Removed/Modified Nodes (Infrastructure, Code, Data)
2. Added/Removed Edges (Lineage, Dependencies)
3. Impact Assessment (Breaking Changes)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set, Optional, Any
from datetime import datetime

from ..core.interfaces import IGraph
from ..core.types import Node, Edge, NodeType, RelationshipType


class ChangeType(str, Enum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    MODIFIED = "MODIFIED"
    UNCHANGED = "UNCHANGED"


@dataclass
class NodeChange:
    """Represents a change to a single node."""
    node_id: str
    name: str
    type: NodeType
    change_type: ChangeType
    details: str = ""
    old_metadata: Dict[str, Any] = field(default_factory=dict)
    new_metadata: Dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        icon = {
            ChangeType.ADDED: "➕",
            ChangeType.REMOVED: "🗑️",
            ChangeType.MODIFIED: "✏️"
        }.get(self.change_type, "?")
        return f"{icon} {self.type.value}: {self.name} ({self.change_type.value})"


@dataclass
class EdgeChange:
    """Represents a change to a dependency (edge)."""
    source_id: str
    target_id: str
    type: RelationshipType
    change_type: ChangeType

    def __str__(self) -> str:
        arrow = "-->"
        if self.type in [RelationshipType.READS, RelationshipType.DEPENDS_ON]:
            arrow = "<--" # Visual cue for dependency vs flow
        
        icon = "➕" if self.change_type == ChangeType.ADDED else "🗑️"
        return f"{icon} {self.source_id} {arrow} {self.target_id} [{self.type.value}]"


@dataclass
class DiffReport:
    """Complete report of graph differences."""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # Detailed changes
    node_changes: List[NodeChange] = field(default_factory=list)
    edge_changes: List[EdgeChange] = field(default_factory=list)
    
    # Quick access lists
    added_nodes: List[Node] = field(default_factory=list)
    removed_nodes: List[Node] = field(default_factory=list)
    modified_nodes: List[Node] = field(default_factory=list)

    @property
    def has_breaking_changes(self) -> bool:
        """
        Heuristic for breaking changes:
        - Removing an Env Var that is read by code? (Edge removal)
        - Removing an Infra resource?
        """
        for nc in self.node_changes:
            if nc.change_type == ChangeType.REMOVED:
                # Removing config/infra is usually risky
                if nc.type in [NodeType.ENV_VAR, NodeType.INFRA_RESOURCE, NodeType.CONFIG_KEY]:
                    return True
        return False

    def to_markdown(self) -> str:
        """Generate a human-readable markdown report."""
        lines = [
            "# 📊 Graph Diff Report",
            f"Generated: {self.timestamp}",
            "",
            "## Summary",
            f"- **Nodes Changed:** {len(self.node_changes)}",
            f"  - Added: {len(self.added_nodes)}",
            f"  - Removed: {len(self.removed_nodes)}",
            f"  - Modified: {len(self.modified_nodes)}",
            f"- **Edges Changed:** {len(self.edge_changes)}",
            ""
        ]

        if self.has_breaking_changes:
            lines.extend(["### ⚠️ POTENTIAL BREAKING CHANGES", ""])

        if self.node_changes:
            lines.extend(["## Node Changes", ""])
            # Group by type
            by_type = {}
            for nc in self.node_changes:
                by_type.setdefault(nc.type.value, []).append(nc)
            
            for ntype, changes in by_type.items():
                lines.append(f"### {ntype.title()}s")
                for c in changes:
                    detail = f" - {c.details}" if c.details else ""
                    lines.append(f"- {str(c)}{detail}")
                lines.append("")

        if self.edge_changes:
            lines.extend(["## Dependency Changes", ""])
            for ec in self.edge_changes:
                lines.append(f"- {str(ec)}")

        return "\n".join(lines)


class DiffAnalyzer:
    """
    Compares two DependencyGraphs to detect structural and semantic changes.
    """

    def compare(self, base_graph: IGraph, head_graph: IGraph) -> DiffReport:
        """
        Compare base (original) vs head (new) graph.
        """
        report = DiffReport()

        # 1. Map Nodes for O(1) lookup
        base_nodes = {n.id: n for n in base_graph.iter_nodes()}
        head_nodes = {n.id: n for n in head_graph.iter_nodes()}

        base_ids = set(base_nodes.keys())
        head_ids = set(head_nodes.keys())

        # 2. Detect Added/Removed Nodes
        for nid in head_ids - base_ids:
            node = head_nodes[nid]
            report.added_nodes.append(node)
            report.node_changes.append(NodeChange(
                node_id=nid, name=node.name, type=node.type, change_type=ChangeType.ADDED
            ))

        for nid in base_ids - head_ids:
            node = base_nodes[nid]
            report.removed_nodes.append(node)
            report.node_changes.append(NodeChange(
                node_id=nid, name=node.name, type=node.type, change_type=ChangeType.REMOVED
            ))

        # 3. Detect Modified Nodes
        for nid in base_ids.intersection(head_ids):
            b_node = base_nodes[nid]
            h_node = head_nodes[nid]
            
            changes = []
            if b_node.path != h_node.path:
                changes.append(f"Moved: {b_node.path} -> {h_node.path}")
            
            if b_node.metadata != h_node.metadata:
                # Robust metadata diff
                b_keys = set(b_node.metadata.keys())
                h_keys = set(h_node.metadata.keys())
                
                added_keys = h_keys - b_keys
                removed_keys = b_keys - h_keys
                
                # Check for value changes in common keys
                changed_keys = []
                for k in b_keys.intersection(h_keys):
                    if b_node.metadata[k] != h_node.metadata[k]:
                        changed_keys.append(k)
                
                details = []
                if added_keys: details.append(f"Meta added: {added_keys}")
                if removed_keys: details.append(f"Meta removed: {removed_keys}")
                if changed_keys: details.append(f"Meta changed: {changed_keys}")
                
                changes.append("; ".join(details))
                
            if changes:
                report.modified_nodes.append(h_node)
                report.node_changes.append(NodeChange(
                    node_id=nid,
                    name=h_node.name,
                    type=h_node.type,
                    change_type=ChangeType.MODIFIED,
                    details=", ".join(changes),
                    old_metadata=b_node.metadata,
                    new_metadata=h_node.metadata
                ))

        # 4. Compare Edges
        # Create a signature for edges: (source, target, type)
        base_edges = {
            (e.source_id, e.target_id, e.type) 
            for e in base_graph.iter_edges()
        }
        head_edges = {
            (e.source_id, e.target_id, e.type) 
            for e in head_graph.iter_edges()
        }

        # Added Edges
        for (src, tgt, rtype) in head_edges - base_edges:
            report.edge_changes.append(EdgeChange(
                source_id=src, target_id=tgt, type=rtype, change_type=ChangeType.ADDED
            ))

        # Removed Edges
        for (src, tgt, rtype) in base_edges - head_edges:
            report.edge_changes.append(EdgeChange(
                source_id=src, target_id=tgt, type=rtype, change_type=ChangeType.REMOVED
            ))

        return report