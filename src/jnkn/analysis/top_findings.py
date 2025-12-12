"""
Top Findings Extractor.

Identifies and ranks the most interesting/important connections
from a jnkn scan to highlight in the summary output.
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Dict, List, Optional

from ..core.graph import DependencyGraph
from ..core.types import Edge, Node, NodeType

logger = logging.getLogger(__name__)


class FindingType(StrEnum):
    """Types of interesting findings."""

    HIGH_CONFIDENCE_LINK = "high_confidence_link"
    AMBIGUOUS_MATCH = "ambiguous_match"
    MISSING_PROVIDER = "missing_provider"
    HIGH_BLAST_RADIUS = "high_blast_radius"
    CROSS_DOMAIN_CHAIN = "cross_domain_chain"
    POTENTIAL_RISK = "potential_risk"


@dataclass
class Finding:
    """A single interesting finding from the scan."""

    type: FindingType
    title: str
    description: str
    confidence: float
    interest_score: float
    source_node: Optional[Node] = None
    target_node: Optional[Node] = None
    edge: Optional[Edge] = None
    blast_radius: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "type": self.type.value,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "interest_score": self.interest_score,
            "blast_radius": self.blast_radius,
            "source": self.source_node.id if self.source_node else None,
            "target": self.target_node.id if self.target_node else None,
            "metadata": self.metadata,
        }


@dataclass
class TopFindingsSummary:
    """Summary of top findings from a scan."""

    findings: List[Finding] = field(default_factory=list)
    total_connections: int = 0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0
    ambiguous_count: int = 0
    missing_providers: int = 0

    def get_top_n(self, n: int = 5) -> List[Finding]:
        """Get the top N most interesting findings."""
        sorted_findings = sorted(self.findings, key=lambda f: f.interest_score, reverse=True)
        return sorted_findings[:n]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "total_connections": self.total_connections,
            "high_confidence_count": self.high_confidence_count,
            "medium_confidence_count": self.medium_confidence_count,
            "low_confidence_count": self.low_confidence_count,
            "ambiguous_count": self.ambiguous_count,
            "missing_providers": self.missing_providers,
            "top_findings": [f.to_dict() for f in self.get_top_n()],
        }


class TopFindingsExtractor:
    """
    Extracts and ranks the most interesting findings from a dependency graph.
    """

    def __init__(self, graph: DependencyGraph):
        self.graph = graph

    def extract(self) -> TopFindingsSummary:
        """
        Extract top findings from the graph.
        """
        summary = TopFindingsSummary()
        findings: List[Finding] = []

        # Get all edges (connections)
        edges = list(self.graph.iter_edges())
        summary.total_connections = len(edges)

        # Track nodes with multiple matches (ambiguous)
        source_match_counts: Dict[str, int] = {}

        for edge in edges:
            source_id = edge.source_id
            source_match_counts[source_id] = source_match_counts.get(source_id, 0) + 1

        # Analyze each edge
        for edge in edges:
            source = self.graph.get_node(edge.source_id)
            target = self.graph.get_node(edge.target_id)
            confidence = edge.confidence or 0.5

            # Count by confidence level
            if confidence >= 0.7:
                summary.high_confidence_count += 1
            elif confidence >= 0.4:
                summary.medium_confidence_count += 1
            else:
                summary.low_confidence_count += 1

            # Calculate interest score
            interest_score = self._calculate_interest(edge, source, target, source_match_counts)

            # Check for ambiguous matches
            is_ambiguous = source_match_counts.get(edge.source_id, 0) > 1
            if is_ambiguous:
                summary.ambiguous_count += 1

            # Create finding
            finding_type = self._determine_finding_type(edge, source, target, is_ambiguous)

            # Calculate blast radius for high-interest findings
            blast_radius = 0
            if interest_score > 2.0 and target:
                try:
                    impacted = self.graph.get_descendants(target.id, max_depth=3)
                    blast_radius = len(impacted)
                except Exception:
                    pass

            finding = Finding(
                type=finding_type,
                title=self._generate_title(source, target, finding_type),
                description=self._generate_description(source, target, edge, is_ambiguous),
                confidence=confidence,
                interest_score=interest_score,
                source_node=source,
                target_node=target,
                edge=edge,
                blast_radius=blast_radius,
                metadata={
                    "is_ambiguous": is_ambiguous,
                    "match_count": source_match_counts.get(edge.source_id, 1),
                },
            )

            findings.append(finding)

        # Find env vars without providers
        summary.missing_providers = self._count_missing_providers()

        # Add missing provider findings
        missing_findings = self._create_missing_provider_findings()
        findings.extend(missing_findings)

        summary.findings = findings
        return summary

    def _calculate_interest(
        self,
        edge: Edge,
        source: Optional[Node],
        target: Optional[Node],
        match_counts: Dict[str, int],
    ) -> float:
        """Calculate an interest score for a connection."""
        score = 0.0
        confidence = edge.confidence or 0.5

        # High confidence connections are interesting
        if confidence >= 0.8:
            score += 2.0
        elif confidence >= 0.6:
            score += 1.0

        # Ambiguous matches are very interesting (need resolution)
        if match_counts.get(edge.source_id, 0) > 1:
            score += 2.5

        # Cross-domain connections are interesting
        if source and target:
            if source.type != target.type:
                score += 1.5

            # Infra connections are particularly interesting
            if target.type == NodeType.INFRA_RESOURCE:
                score += 1.0

        # Low confidence with cross-domain is interesting (potential issue)
        if confidence < 0.5 and source and target and source.type != target.type:
            score += 1.0

        return score

    def _determine_finding_type(
        self,
        edge: Edge,
        source: Optional[Node],
        target: Optional[Node],
        is_ambiguous: bool,
    ) -> FindingType:
        """Determine the type of finding."""
        confidence = edge.confidence or 0.5

        if is_ambiguous:
            return FindingType.AMBIGUOUS_MATCH

        if confidence >= 0.8:
            return FindingType.HIGH_CONFIDENCE_LINK

        if source and target and source.type != target.type:
            return FindingType.CROSS_DOMAIN_CHAIN

        if confidence < 0.4:
            return FindingType.POTENTIAL_RISK

        return FindingType.HIGH_CONFIDENCE_LINK

    def _generate_title(
        self,
        source: Optional[Node],
        target: Optional[Node],
        finding_type: FindingType,
    ) -> str:
        """Generate a human-readable title for the finding."""
        source_name = source.name if source else "Unknown"
        target_name = target.name if target else "Unknown"

        if finding_type == FindingType.AMBIGUOUS_MATCH:
            return f"{source_name} has multiple potential matches"
        elif finding_type == FindingType.HIGH_CONFIDENCE_LINK:
            return f"{source_name} → {target_name}"
        elif finding_type == FindingType.MISSING_PROVIDER:
            return f"{source_name} has no infrastructure provider"
        elif finding_type == FindingType.CROSS_DOMAIN_CHAIN:
            return f"Cross-domain: {source_name} → {target_name}"
        else:
            return f"{source_name} connection"

    def _generate_description(
        self,
        source: Optional[Node],
        target: Optional[Node],
        edge: Edge,
        is_ambiguous: bool,
    ) -> str:
        """Generate a description explaining the finding."""
        confidence = edge.confidence or 0.5
        confidence_pct = int(confidence * 100)

        if is_ambiguous:
            return (
                "This variable matches multiple infrastructure outputs. "
                "Consider using more specific naming to clarify the connection."
            )

        if confidence >= 0.8:
            return (
                f"Strong match ({confidence_pct}% confidence). "
                f"Token patterns align well between source and target."
            )
        elif confidence >= 0.5:
            return (
                f"Moderate match ({confidence_pct}% confidence). "
                f"Review to confirm this is an intentional connection."
            )
        else:
            return (
                f"Weak match ({confidence_pct}% confidence). "
                f"This may be a false positive - consider suppressing if incorrect."
            )

    def _count_missing_providers(self) -> int:
        """Count environment variables with no infrastructure provider."""
        count = 0
        env_nodes = self.graph.get_nodes_by_type(NodeType.ENV_VAR)

        for node in env_nodes:
            # Check if this node has any outgoing edges to infra
            out_edges = self.graph.get_out_edges(node.id)
            has_infra = any(e.target_id.startswith("infra:") for e in out_edges)
            if not has_infra:
                count += 1

        return count

    def _create_missing_provider_findings(self) -> List[Finding]:
        """Create findings for env vars missing providers."""
        findings = []
        env_nodes = self.graph.get_nodes_by_type(NodeType.ENV_VAR)

        for node in env_nodes:
            out_edges = self.graph.get_out_edges(node.id)
            has_infra = any(e.target_id.startswith("infra:") for e in out_edges)

            if not has_infra:
                finding = Finding(
                    type=FindingType.MISSING_PROVIDER,
                    title=f"{node.name} has no infrastructure provider",
                    description=(
                        "This environment variable is not linked to any "
                        "infrastructure output. Is it set manually in deployment? "
                        "Consider documenting its source."
                    ),
                    confidence=0.0,
                    interest_score=2.0,
                    source_node=node,
                    target_node=None,
                    edge=None,
                    metadata={"file": node.path},
                )
                findings.append(finding)

        return findings
