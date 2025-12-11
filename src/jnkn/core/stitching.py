"""
Cross-domain dependency stitching.

Refactored to use the Collect-then-Apply pattern.
Phase 1: Read-only analysis creates a StitchingPlan.
Phase 2: Write-only application mutates the graph.
This prevents "mutation during iteration" errors common in Rust.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple

from .confidence import create_default_calculator
from .graph import DependencyGraph
from .types import Edge, MatchResult, MatchStrategy, Node, NodeType, RelationshipType


@dataclass
class StitchingPlan:
    """
    Immutable plan of edges to add to the graph.
    """
    edges_to_add: List[Edge] = field(default_factory=list)

    def merge(self, other: "StitchingPlan") -> "StitchingPlan":
        """Combine two plans into a new one."""
        return StitchingPlan(
            edges_to_add=self.edges_to_add + other.edges_to_add
        )


class MatchConfig:
    """Configuration for the fuzzy matching engine."""
    def __init__(
        self,
        min_confidence: float = 0.5,
        min_token_overlap: int = 2,
        min_token_length: int = 2,
    ):
        self.min_confidence = min_confidence
        self.min_token_overlap = min_token_overlap
        self.min_token_length = min_token_length


class TokenMatcher:
    """Utility class for token-based matching operations."""

    @staticmethod
    def normalize(name: str) -> str:
        result = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            result = result.replace(sep, "")
        return result

    @staticmethod
    def tokenize(name: str) -> List[str]:
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]


class StitchingRule(ABC):
    """Abstract base class for all stitching rules."""

    def __init__(self, config: MatchConfig | None = None):
        self.config = config or MatchConfig()
        self.calculator = create_default_calculator()

    @abstractmethod
    def plan(self, graph: DependencyGraph) -> StitchingPlan:
        """
        Analyze the graph and return a plan of edges to add.
        MUST NOT mutate the graph.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        pass


class EnvVarToInfraRule(StitchingRule):
    """
    Stitching rule that links environment variables to infrastructure resources.
    """

    def get_name(self) -> str:
        return "EnvVarToInfraRule"

    def plan(self, graph: DependencyGraph) -> StitchingPlan:
        edges = []
        
        # Get targets (Consumers)
        env_nodes = graph.get_nodes_by_type(NodeType.ENV_VAR)
        
        # Get sources (Providers)
        infra_nodes = graph.get_nodes_by_type(NodeType.INFRA_RESOURCE)
        infra_nodes.extend(graph.get_nodes_by_type(NodeType.CONFIG_KEY))

        if not env_nodes or not infra_nodes:
            return StitchingPlan()

        # Index infra nodes for performance
        infra_by_norm = defaultdict(list)
        infra_by_token = defaultdict(list)

        for infra in infra_nodes:
            norm = TokenMatcher.normalize(infra.name)
            infra_by_norm[norm].append(infra)
            
            tokens = infra.tokens or TokenMatcher.tokenize(infra.name)
            for t in tokens:
                if len(t) >= self.config.min_token_length:
                    infra_by_token[t].append(infra)

        for env in env_nodes:
            env_norm = TokenMatcher.normalize(env.name)
            env_tokens = env.tokens or TokenMatcher.tokenize(env.name)
            
            candidates = set()
            
            # Exact/Normalized Matches
            for infra in infra_by_norm.get(env_norm, []):
                candidates.add(infra)
            
            # Token Overlap Candidates
            for t in env_tokens:
                if len(t) >= self.config.min_token_length:
                    for infra in infra_by_token.get(t, []):
                        candidates.add(infra)

            best_match: MatchResult | None = None
            
            # Evaluate all candidates
            for infra in candidates:
                result = self.calculator.calculate(
                    source_name=infra.name,
                    target_name=env.name,
                    source_tokens=infra.tokens or TokenMatcher.tokenize(infra.name),
                    target_tokens=env_tokens,
                    source_type=infra.type,
                    target_type=env.type,
                    alternative_match_count=len(candidates) - 1
                )

                if result.score >= self.config.min_confidence:
                    if best_match is None or result.score > best_match.confidence:
                        best_match = MatchResult(
                            source_node=infra.id,
                            target_node=env.id,
                            strategy=MatchStrategy.SEMANTIC,
                            confidence=result.score,
                            matched_tokens=result.matched_tokens,
                            explanation=result.explanation
                        )

            if best_match:
                edges.append(best_match.to_edge(RelationshipType.PROVIDES, self.get_name()))

        return StitchingPlan(edges_to_add=edges)


class InfraToInfraRule(StitchingRule):
    """
    Stitching rule that links infrastructure resources to other resources.
    """

    def get_name(self) -> str:
        return "InfraToInfraRule"

    def plan(self, graph: DependencyGraph) -> StitchingPlan:
        edges = []
        infra_nodes = graph.get_nodes_by_type(NodeType.INFRA_RESOURCE)

        if len(infra_nodes) < 2:
            return StitchingPlan()

        nodes_by_token = defaultdict(list)
        for node in infra_nodes:
            tokens = node.tokens or TokenMatcher.tokenize(node.name)
            for t in tokens:
                if len(t) >= self.config.min_token_length:
                    nodes_by_token[t].append(node)

        seen_pairs = set()

        for token, nodes in nodes_by_token.items():
            if len(nodes) < 2: continue
            
            for i, n1 in enumerate(nodes):
                for n2 in nodes[i+1:]:
                    pair = tuple(sorted([n1.id, n2.id]))
                    if pair in seen_pairs: continue
                    seen_pairs.add(pair)

                    source, target = self._determine_direction(n1, n2)
                    
                    result = self.calculator.calculate(
                        source_name=source.name,
                        target_name=target.name,
                        source_tokens=source.tokens or [],
                        target_tokens=target.tokens or [],
                        source_type=source.type,
                        target_type=target.type
                    )

                    if result.score >= self.config.min_confidence:
                        edges.append(Edge(
                            source_id=source.id,
                            target_id=target.id,
                            type=RelationshipType.CONFIGURES,
                            confidence=result.score,
                            match_strategy=MatchStrategy.TOKEN_OVERLAP,
                            metadata={
                                "rule": self.get_name(),
                                "explanation": result.explanation,
                                "matched_tokens": result.matched_tokens
                            }
                        ))
        return StitchingPlan(edges_to_add=edges)

    def _determine_direction(self, n1: Node, n2: Node) -> Tuple[Node, Node]:
        hierarchy = {
            "vpc": 10, "subnet": 9, "security_group": 8, "iam": 7,
            "rds": 5, "db": 5, "instance": 4, "lambda": 3, "s3": 3
        }
        
        def score(n):
            for k, v in hierarchy.items():
                if k in n.name.lower(): return v
            return 0
            
        if score(n1) >= score(n2):
            return n1, n2
        return n2, n1


class Stitcher:
    """Orchestrator for stitching rules using Two-Phase Commit."""
    
    def __init__(self, config: MatchConfig | None = None):
        self.config = config or MatchConfig()
        self.rules = [
            EnvVarToInfraRule(self.config),
            InfraToInfraRule(self.config)
        ]

    def stitch(self, graph: DependencyGraph) -> List[Edge]:
        """
        Run the stitching process in two phases.
        
        1. Collect: Run all rules to generate a plan.
        2. Apply: Mutate the graph in one go.
        """
        # Phase 1: Collect (Read-Only)
        plan = StitchingPlan()
        for rule in self.rules:
            try:
                rule_plan = rule.plan(graph)
                plan = plan.merge(rule_plan)
            except Exception as e:
                print(f"Rule {rule.get_name()} failed: {e}")

        # Phase 2: Apply (Write-Only)
        added_edges = []
        for edge in plan.edges_to_add:
            if not graph.has_edge(edge.source_id, edge.target_id):
                graph.add_edge(edge)
                added_edges.append(edge)
        
        return added_edges
