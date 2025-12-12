"""
Match Explanation Generator for jnkn.

This module provides detailed explanations of why matches were made,
including all signals considered, their scores, and alternative matches
that were rejected.

Features:
- Detailed breakdown of matching process
- Shows all signals and their contributions
- Lists alternative matches that were rejected
- Human-readable formatted output
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List

from ..core.confidence import (
    ConfidenceCalculator,
    ConfidenceResult,
    create_default_calculator,
)
from ..core.graph import DependencyGraph
from ..core.types import NodeType

logger = logging.getLogger(__name__)


@dataclass
class NodeInfo:
    """Information about a node for explanation."""

    id: str
    name: str
    type: str
    tokens: List[str]
    path: str | None = None
    line_number: int | None = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlternativeMatch:
    """An alternative match that was considered but rejected."""

    node_id: str
    node_name: str
    score: float
    rejection_reason: str
    matched_tokens: List[str] = field(default_factory=list)


@dataclass
class MatchExplanation:
    """Complete explanation of a match."""

    source: NodeInfo
    target: NodeInfo
    confidence_result: ConfidenceResult
    alternatives: List[AlternativeMatch] = field(default_factory=list)
    edge_exists: bool = False
    edge_metadata: Dict[str, Any] = field(default_factory=dict)


class ExplanationGenerator:
    """
    Generate detailed explanations for dependency matches.

    Usage:
        generator = ExplanationGenerator(graph)
        explanation = generator.explain("env:PAYMENT_DB_HOST", "infra:payment_db_host")
        print(generator.format(explanation))
    """

    def __init__(
        self,
        graph: DependencyGraph | None = None,
        calculator: ConfidenceCalculator | None = None,
        min_confidence: float = 0.5,
    ):
        """
        Initialize the explanation generator.

        Args:
            graph: DependencyGraph instance for looking up nodes
            calculator: ConfidenceCalculator for scoring matches
            min_confidence: Minimum confidence threshold for matches
        """
        self.graph = graph
        self.calculator = calculator or create_default_calculator()
        self.min_confidence = min_confidence

    def explain(
        self,
        source_id: str,
        target_id: str,
        find_alternatives: bool = True,
    ) -> MatchExplanation:
        """
        Generate a detailed explanation for a match.

        Args:
            source_id: Source node ID (e.g., "env:PAYMENT_DB_HOST")
            target_id: Target node ID (e.g., "infra:payment_db_host")
            find_alternatives: Whether to find alternative matches

        Returns:
            MatchExplanation with all details
        """
        # Get source node info
        source_info = self._get_node_info(source_id)
        target_info = self._get_node_info(target_id)

        # Calculate confidence
        confidence_result = self.calculator.calculate(
            source_name=source_info.name,
            target_name=target_info.name,
            source_tokens=source_info.tokens,
            target_tokens=target_info.tokens,
            source_node_id=source_id,
            target_node_id=target_id,
        )

        # Check if edge exists
        edge_exists = False
        edge_metadata = {}
        if self.graph:
            edge = self.graph.get_edge(source_id, target_id)
            if edge:
                edge_exists = True
                edge_metadata = edge.metadata or {}

        # Find alternative matches
        alternatives = []
        if find_alternatives and self.graph:
            alternatives = self._find_alternatives(source_info, target_id)

        return MatchExplanation(
            source=source_info,
            target=target_info,
            confidence_result=confidence_result,
            alternatives=alternatives,
            edge_exists=edge_exists,
            edge_metadata=edge_metadata,
        )

    def explain_why_not(
        self,
        source_id: str,
        target_id: str,
    ) -> str:
        """
        Explain why a match was NOT made.

        Useful for debugging missing connections.

        Args:
            source_id: Source node ID
            target_id: Target node ID

        Returns:
            Human-readable explanation
        """
        explanation = self.explain(source_id, target_id, find_alternatives=False)

        lines = []
        lines.append("=" * 60)
        lines.append("WHY NO MATCH?")
        lines.append("=" * 60)
        lines.append("")

        score = explanation.confidence_result.score

        if score < self.min_confidence:
            lines.append(f"X Score ({score:.2f}) is below threshold ({self.min_confidence:.2f})")
            lines.append("")
            lines.append("Details:")
            lines.append(f"  Source: {source_id}")
            lines.append(f"  Target: {target_id}")
            lines.append(f"  Source tokens: {explanation.source.tokens}")
            lines.append(f"  Target tokens: {explanation.target.tokens}")
            lines.append("")

            # Find common tokens
            source_set = set(explanation.source.tokens)
            target_set = set(explanation.target.tokens)
            common = source_set & target_set

            if not common:
                lines.append("  ! No overlapping tokens found")
            else:
                lines.append(f"  Common tokens: {list(common)}")

            # Show what would need to change
            needed = self.min_confidence - score
            lines.append("")
            lines.append(f"  To reach threshold, need +{needed:.2f} confidence")

            if explanation.confidence_result.penalties:
                lines.append("")
                lines.append("  Penalties applied:")
                for p in explanation.confidence_result.penalties:
                    lines.append(f"    - {p.get('penalty_type')}: x{p.get('multiplier', 1.0):.2f}")

        elif explanation.edge_exists:
            lines.append("V Match DOES exist!")
            lines.append(f"  Score: {score:.2f}")

        else:
            lines.append(f"? Score ({score:.2f}) is above threshold, but no edge found")
            lines.append("  This might indicate the stitcher hasn't run yet")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def format(self, explanation: MatchExplanation) -> str:
        """
        Format an explanation for CLI output.

        Args:
            explanation: MatchExplanation to format

        Returns:
            Formatted string for display
        """
        lines = []

        # Header
        lines.append("=" * 60)
        lines.append("MATCH EXPLANATION")
        lines.append("=" * 60)
        lines.append("")

        # Source info
        lines.append(f"Source: {explanation.source.id}")
        lines.append(f"  Type: {explanation.source.type}")
        lines.append(f"  Tokens: {explanation.source.tokens}")
        if explanation.source.path:
            loc = explanation.source.path
            if explanation.source.line_number:
                loc += f":{explanation.source.line_number}"
            lines.append(f"  Found in: {loc}")
        lines.append("")

        # Target info
        lines.append(f"Target: {explanation.target.id}")
        lines.append(f"  Type: {explanation.target.type}")
        lines.append(f"  Tokens: {explanation.target.tokens}")
        if explanation.target.path:
            loc = explanation.target.path
            if explanation.target.line_number:
                loc += f":{explanation.target.line_number}"
            lines.append(f"  Found in: {loc}")
        lines.append("")

        # Confidence calculation
        lines.append("-" * 60)
        lines.append("CONFIDENCE CALCULATION")
        lines.append("-" * 60)
        lines.append("")

        lines.append("Base signals:")
        if explanation.confidence_result.signals:
            for signal in explanation.confidence_result.signals:
                weight = signal.get("weight", 0)
                name = signal.get("signal", "unknown")
                details = signal.get("details", "")
                matched_tokens = signal.get("matched_tokens", [])

                if matched_tokens:
                    lines.append(f"  [+{weight:.2f}] {name}: {matched_tokens}")
                elif details:
                    lines.append(f"  [+{weight:.2f}] {name}")
                    lines.append(f"         {details}")
                else:
                    lines.append(f"  [+{weight:.2f}] {name}")
        else:
            lines.append("  (none matched)")

        lines.append("")
        lines.append("Penalties:")
        if explanation.confidence_result.penalties:
            for penalty in explanation.confidence_result.penalties:
                multiplier = penalty.get("multiplier", 1.0)
                name = penalty.get("penalty_type", "unknown")
                reason = penalty.get("reason", "")
                lines.append(f"  [x{multiplier:.2f}] {name}")
                if reason:
                    lines.append(f"         {reason}")
        else:
            lines.append("  None applied")

        lines.append("")

        # Final score
        score = explanation.confidence_result.score
        level = self._get_confidence_level(score)
        lines.append(f"Final confidence: {score:.2f} ({level})")

        # Edge status
        if explanation.edge_exists:
            lines.append("")
            lines.append("Edge Status: EXISTS in graph")
            if explanation.edge_metadata:
                for key, value in explanation.edge_metadata.items():
                    if key not in ("rule", "matched_tokens", "explanation"):
                        lines.append(f"  {key}: {value}")
        else:
            lines.append("")
            if score >= self.min_confidence:
                lines.append("Edge Status: Would be created (above threshold)")
            else:
                lines.append("Edge Status: Would be REJECTED (below threshold)")

        # Alternatives
        if explanation.alternatives:
            lines.append("")
            lines.append("-" * 60)
            lines.append("ALTERNATIVE MATCHES CONSIDERED")
            lines.append("-" * 60)
            lines.append("")

            for alt in sorted(explanation.alternatives, key=lambda x: -x.score):
                lines.append(f"{alt.node_id} -- Score: {alt.score:.2f} ({alt.rejection_reason})")
                if alt.matched_tokens:
                    lines.append(f"  Tokens: {alt.matched_tokens}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)

    def format_brief(self, explanation: MatchExplanation) -> str:
        """
        Format a brief, single-line explanation.

        Args:
            explanation: MatchExplanation to format

        Returns:
            Brief formatted string
        """
        score = explanation.confidence_result.score
        level = self._get_confidence_level(score)
        status = (
            "EXISTS"
            if explanation.edge_exists
            else "would be created"
            if score >= self.min_confidence
            else "rejected"
        )

        return (
            f"{explanation.source.id} -> {explanation.target.id}: {score:.2f} ({level}, {status})"
        )

    def _get_node_info(self, node_id: str) -> NodeInfo:
        """
        Get node information from graph or infer from ID.

        Args:
            node_id: Node ID to look up

        Returns:
            NodeInfo with available details
        """
        # Try to get from graph
        if self.graph:
            node = self.graph.get_node(node_id)
            if node:
                return NodeInfo(
                    id=node.id,
                    name=node.name,
                    type=node.type.value,
                    tokens=list(node.tokens),
                    path=node.path,
                    line_number=node.metadata.get("line") if node.metadata else None,
                    metadata=dict(node.metadata) if node.metadata else {},
                )

        # Infer from ID
        name = self._extract_name_from_id(node_id)
        node_type = self._infer_type_from_id(node_id)
        tokens = self._tokenize(name)

        return NodeInfo(
            id=node_id,
            name=name,
            type=node_type,
            tokens=tokens,
        )

    def _find_alternatives(
        self,
        source_info: NodeInfo,
        actual_target_id: str,
        max_alternatives: int = 5,
    ) -> List[AlternativeMatch]:
        """
        Find alternative matches that were considered.

        Args:
            source_info: Source node info
            actual_target_id: The target that was actually matched
            max_alternatives: Maximum alternatives to return

        Returns:
            List of alternative matches
        """
        if not self.graph:
            return []

        alternatives = []

        # Determine what type of nodes to look at based on source type
        if source_info.id.startswith("env:"):
            candidate_types = [NodeType.INFRA_RESOURCE]
        elif source_info.id.startswith("infra:"):
            candidate_types = [NodeType.INFRA_RESOURCE, NodeType.ENV_VAR]
        else:
            candidate_types = [NodeType.INFRA_RESOURCE, NodeType.ENV_VAR, NodeType.DATA_ASSET]

        # Get candidate nodes
        candidates = []
        for node_type in candidate_types:
            candidates.extend(self.graph.get_nodes_by_type(node_type))

        # Score each candidate
        for candidate in candidates:
            if candidate.id == actual_target_id:
                continue

            result = self.calculator.calculate(
                source_name=source_info.name,
                target_name=candidate.name,
                source_tokens=source_info.tokens,
                target_tokens=list(candidate.tokens),
            )

            # Only include if there's some signal
            if result.score > 0:
                if result.score < self.min_confidence:
                    reason = f"rejected: below threshold ({self.min_confidence})"
                else:
                    reason = "not selected: lower score than match"

                alternatives.append(
                    AlternativeMatch(
                        node_id=candidate.id,
                        node_name=candidate.name,
                        score=result.score,
                        rejection_reason=reason,
                        matched_tokens=result.matched_tokens,
                    )
                )

        # Sort by score and limit
        alternatives.sort(key=lambda x: -x.score)
        return alternatives[:max_alternatives]

    def _get_confidence_level(self, score: float) -> str:
        """Get human-readable confidence level."""
        if score >= 0.8:
            return "HIGH"
        elif score >= 0.6:
            return "MEDIUM"
        elif score >= 0.4:
            return "LOW"
        else:
            return "VERY LOW"

    @staticmethod
    def _extract_name_from_id(node_id: str) -> str:
        """Extract node name from ID."""
        # Handle common ID formats
        # Check for :// first (e.g. file://path/to/file)
        if "://" in node_id:
            return node_id.split("://", 1)[1]
        # Then check for : (e.g. env:VAR)
        if ":" in node_id:
            return node_id.split(":", 1)[1]
        return node_id

    @staticmethod
    def _infer_type_from_id(node_id: str) -> str:
        """Infer node type from ID prefix."""
        if node_id.startswith("env:"):
            return "env_var"
        elif node_id.startswith("infra:"):
            return "infra_resource"
        elif node_id.startswith("file://"):
            return "code_file"
        elif node_id.startswith("entity:"):
            return "code_entity"
        elif node_id.startswith("data:"):
            return "data_asset"
        else:
            return "unknown"

    @staticmethod
    def _tokenize(name: str) -> List[str]:
        """Split name into tokens."""
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]


def create_explanation_generator(
    graph: DependencyGraph | None = None,
    min_confidence: float = 0.5,
) -> ExplanationGenerator:
    """
    Factory function to create an ExplanationGenerator.

    Args:
        graph: Optional DependencyGraph
        min_confidence: Minimum confidence threshold

    Returns:
        Configured ExplanationGenerator
    """
    return ExplanationGenerator(
        graph=graph,
        calculator=create_default_calculator(),
        min_confidence=min_confidence,
    )
