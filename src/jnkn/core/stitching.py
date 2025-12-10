"""
Cross-domain dependency stitching.

This module implements the core "glue" logic that connects disparate domains:
- Environment variables to infrastructure resources
- Code references to data assets
- Configuration keys to their providers

Key capabilities include:
- Linking environment variables to infrastructure resources (e.g., `PAYMENT_DB_HOST` -> `aws_db_instance.payment`).
- Linking infrastructure resources to each other (e.g., Security Groups to EC2 instances).
- Configurable confidence scoring to minimize false positives.

The stitching process transforms a collection of isolated nodes (from parsing) into a
connected graph that represents the full system architecture.
"""

from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from .graph import DependencyGraph
from .types import Edge, MatchResult, MatchStrategy, Node, NodeType, RelationshipType


class MatchConfig:
    """
    Configuration for the fuzzy matching engine.

    Controls the thresholds and weights used to determine if two artifacts are related.

    Attributes:
        min_confidence (float): The minimum score (0.0 - 1.0) required to create an edge.
            Defaults to 0.5.
        min_token_overlap (int): The minimum number of shared tokens required for a match.
            Defaults to 2.
        min_token_length (int): Tokens shorter than this length are ignored to reduce noise.
            Defaults to 2.
        strategy_weights (Dict[MatchStrategy, float]): A mapping of matching strategies to
            their base confidence scores.
    """

    def __init__(
        self,
        min_confidence: float = 0.5,
        min_token_overlap: int = 2,
        min_token_length: int = 2,
        strategy_weights: Optional[Dict[MatchStrategy, float]] = None,
    ):
        """
        Initialize the match configuration.

        Args:
            min_confidence: Minimum score (0.0-1.0) to accept a match.
            min_token_overlap: Minimum shared tokens required.
            min_token_length: Minimum character length for valid tokens.
            strategy_weights: Optional overrides for strategy scoring weights.
        """
        self.min_confidence = min_confidence
        self.min_token_overlap = min_token_overlap
        self.min_token_length = min_token_length
        self.strategy_weights = strategy_weights or {
            MatchStrategy.EXACT: 1.0,
            MatchStrategy.NORMALIZED: 0.95,
            MatchStrategy.TOKEN_OVERLAP: 0.85,
            MatchStrategy.SUFFIX: 0.75,
            MatchStrategy.PREFIX: 0.75,
            MatchStrategy.CONTAINS: 0.6,
        }


class TokenMatcher:
    """
    Utility class for token-based matching operations.

    Provides static methods for normalizing names, tokenizing strings, and
    calculating similarity scores between token sets.
    """

    @staticmethod
    def normalize(name: str) -> str:
        """
        Normalize a name by lowercasing and removing separators.

        This allows matching across different casing styles (snake_case vs camelCase).

        Args:
            name: The raw name string.

        Returns:
            str: The normalized string (lowercase, no separators).

        Example:
            >>> TokenMatcher.normalize("Payment_DB_Host")
            "paymentdbhost"
        """
        result = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            result = result.replace(sep, "")
        return result

    @staticmethod
    def tokenize(name: str) -> List[str]:
        """
        Split a name into constituent tokens.

        Splits on common separators like underscores, dots, hyphens, and slashes.

        Args:
            name: The raw name string.

        Returns:
            List[str]: A list of lowercase tokens.

        Example:
            >>> TokenMatcher.tokenize("Payment_DB_Host")
            ['payment', 'db', 'host']
        """
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]

    @staticmethod
    def significant_token_overlap(
        tokens1: List[str],
        tokens2: List[str],
        min_length: int = 2
    ) -> Tuple[List[str], float]:
        """
        Calculate the overlap between two token lists, filtering out insignificant tokens.

        Computes the Jaccard similarity coefficient for tokens that meet the minimum length requirement.

        Args:
            tokens1: The first list of tokens.
            tokens2: The second list of tokens.
            min_length: The minimum length for a token to be considered significant.

        Returns:
            Tuple[List[str], float]: A tuple containing:
                - A list of overlapping tokens.
                - The calculated similarity score (0.0 - 1.0).
        """
        sig1 = [t for t in tokens1 if len(t) >= min_length]
        sig2 = [t for t in tokens2 if len(t) >= min_length]
        
        set1 = set(sig1)
        set2 = set(sig2)
        overlap = set1 & set2
        union = set1 | set2

        if not union:
            return [], 0.0

        jaccard = len(overlap) / len(union)
        return list(overlap), jaccard


class StitchingRule(ABC):
    """
    Abstract base class for all stitching rules.

    A stitching rule defines logic to discover implicit relationships between
    nodes in the dependency graph. Subclasses must implement the `apply` method.

    Attributes:
        config (MatchConfig): The configuration used for scoring matches.
    """

    def __init__(self, config: Optional[MatchConfig] = None):
        """
        Initialize the rule.

        Args:
            config: Optional match configuration. Uses defaults if None.
        """
        self.config = config or MatchConfig()

    @abstractmethod
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        """
        Apply this rule to discover new edges in the graph.

        Args:
            graph: The dependency graph to analyze.

        Returns:
            List[Edge]: A list of newly discovered edges.
        """
        pass

    @abstractmethod
    def get_name(self) -> str:
        """
        Return a descriptive, unique name for this rule.

        Returns:
            str: The rule name (e.g., 'EnvVarToInfraRule').
        """
        pass


class EnvVarToInfraRule(StitchingRule):
    """
    Stitching rule that links environment variables to infrastructure resources.

    This rule attempts to find the infrastructure resource that *provides* the value
    for a given environment variable. It uses strategies like normalized name matching
    and token overlap.

    Directionality:
        Infra Resource (or Output) -> PROVIDES -> Environment Variable
    """

    def get_name(self) -> str:
        """Get the rule name."""
        return "EnvVarToInfraRule"

    def apply(self, graph: DependencyGraph) -> List[Edge]:
        """
        Execute the rule logic against the graph.

        Finds potential matches between `ENV_VAR` nodes and `INFRA_RESOURCE`/`CONFIG_KEY` nodes.

        Args:
            graph: The dependency graph.

        Returns:
            List[Edge]: Discovered edges with confidence scores and metadata.
        """
        edges = []

        # Get all env var nodes
        env_nodes = graph.get_nodes_by_type(NodeType.ENV_VAR)
        if not env_nodes:
            # Also check data assets that might be env vars (legacy behavior support)
            env_nodes = [
                n for n in graph.get_nodes_by_type(NodeType.DATA_ASSET)
                if n.id.startswith("env:")
            ]

        # Get all infra nodes
        # Include CONFIG_KEY nodes (Terraform Outputs) as potential providers
        infra_nodes = graph.get_nodes_by_type(NodeType.INFRA_RESOURCE)
        infra_nodes.extend(graph.get_nodes_by_type(NodeType.CONFIG_KEY))

        if not env_nodes or not infra_nodes:
            return edges

        # Build lookup structures for infra nodes
        infra_by_normalized: Dict[str, List[Node]] = defaultdict(list)
        infra_by_tokens: Dict[str, List[Node]] = defaultdict(list)

        for infra in infra_nodes:
            normalized = TokenMatcher.normalize(infra.name)
            infra_by_normalized[normalized].append(infra)

            tokens = infra.tokens or TokenMatcher.tokenize(infra.name)
            for token in tokens:
                if len(token) >= self.config.min_token_length:
                    infra_by_tokens[token].append(infra)

        # Match each env var
        for env in env_nodes:
            env_normalized = TokenMatcher.normalize(env.name)
            env_tokens = env.tokens or TokenMatcher.tokenize(env.name)

            best_matches: Dict[str, MatchResult] = {}

            # Strategy 1: Exact normalized match
            for infra in infra_by_normalized.get(env_normalized, []):
                match = MatchResult(
                    source_node=infra.id,  # Infra is source
                    target_node=env.id,    # Env is target
                    strategy=MatchStrategy.NORMALIZED,
                    confidence=self.config.strategy_weights[MatchStrategy.NORMALIZED],
                    matched_tokens=env_tokens,
                    explanation=f"Normalized match: '{env.name}' == '{infra.name}'"
                )
                self._update_best_match(best_matches, infra.id, match)

            # Strategy 2: Token overlap
            candidate_infra: Set[str] = set()
            for token in env_tokens:
                if len(token) >= self.config.min_token_length:
                    for infra in infra_by_tokens.get(token, []):
                        candidate_infra.add(infra.id)

            for infra_id in candidate_infra:
                infra = graph.get_node(infra_id)
                if not infra:
                    continue

                infra_tokens = infra.tokens or TokenMatcher.tokenize(infra.name)
                overlap, score = TokenMatcher.significant_token_overlap(
                    env_tokens, infra_tokens, self.config.min_token_length
                )

                if len(overlap) >= self.config.min_token_overlap:
                    confidence = min(
                        self.config.strategy_weights[MatchStrategy.TOKEN_OVERLAP],
                        score + (len(overlap) * 0.1)
                    )

                    match = MatchResult(
                        source_node=infra.id,
                        target_node=env.id,
                        strategy=MatchStrategy.TOKEN_OVERLAP,
                        confidence=confidence,
                        matched_tokens=overlap,
                        explanation=f"Token overlap: {overlap} (score: {score:.2f})"
                    )
                    self._update_best_match(best_matches, infra_id, match)

            # Create edges for matches above threshold
            for infra_id, match in best_matches.items():
                if match.confidence >= self.config.min_confidence:
                    edges.append(Edge(
                        source_id=infra_id,
                        target_id=env.id,
                        type=RelationshipType.PROVIDES,
                        confidence=match.confidence,
                        match_strategy=match.strategy,
                        metadata={
                            "rule": self.get_name(),
                            "matched_tokens": match.matched_tokens,
                            "explanation": match.explanation,
                        }
                    ))

        return edges

    def _update_best_match(
        self,
        best_matches: Dict[str, MatchResult],
        target_id: str,
        new_match: MatchResult
    ) -> None:
        """
        Update the best match dictionary if the new match has higher confidence.

        Args:
            best_matches: The dictionary tracking best matches per target ID.
            target_id: The ID of the target node being matched.
            new_match: The new MatchResult candidate.
        """
        if target_id not in best_matches:
            best_matches[target_id] = new_match
        elif new_match.confidence > best_matches[target_id].confidence:
            best_matches[target_id] = new_match


class InfraToInfraRule(StitchingRule):
    """
    Stitching rule that links infrastructure resources to other infrastructure resources.

    This rule identifies dependencies between resources based on naming conventions,
    such as a Security Group referencing a VPC by name token overlap.

    Directionality:
        Determined hierarchically (e.g., VPC configures Subnet).
    """

    def get_name(self) -> str:
        """Get the rule name."""
        return "InfraToInfraRule"

    def apply(self, graph: DependencyGraph) -> List[Edge]:
        """
        Execute the rule logic against the graph.

        Args:
            graph: The dependency graph.

        Returns:
            List[Edge]: Discovered edges between infrastructure resources.
        """
        edges = []
        infra_nodes = graph.get_nodes_by_type(NodeType.INFRA_RESOURCE)

        if len(infra_nodes) < 2:
            return edges

        # Group by shared significant tokens
        nodes_by_token: Dict[str, List[Node]] = defaultdict(list)
        for node in infra_nodes:
            tokens = node.tokens or TokenMatcher.tokenize(node.name)
            for token in tokens:
                if len(token) >= self.config.min_token_length:
                    nodes_by_token[token].append(node)

        seen_pairs: Set[Tuple[str, str]] = set()

        for token, nodes in nodes_by_token.items():
            if len(nodes) < 2:
                continue

            for i, node1 in enumerate(nodes):
                for node2 in nodes[i+1:]:
                    pair = tuple(sorted([node1.id, node2.id]))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)

                    tokens1 = node1.tokens or TokenMatcher.tokenize(node1.name)
                    tokens2 = node2.tokens or TokenMatcher.tokenize(node2.name)
                    overlap, score = TokenMatcher.significant_token_overlap(
                        tokens1, tokens2, self.config.min_token_length
                    )

                    if len(overlap) >= self.config.min_token_overlap and score >= 0.3:
                        source, target = self._determine_direction(node1, node2)

                        edges.append(Edge(
                            source_id=source.id,
                            target_id=target.id,
                            type=RelationshipType.CONFIGURES,
                            confidence=min(0.6, score),
                            match_strategy=MatchStrategy.TOKEN_OVERLAP,
                            metadata={
                                "rule": self.get_name(),
                                "matched_tokens": overlap,
                            }
                        ))

        return edges

    def _determine_direction(self, node1: Node, node2: Node) -> Tuple[Node, Node]:
        """
        Determine edge direction based on resource type hierarchy.

        Uses a predefined hierarchy to establish parent/child relationships
        (e.g., VPC is higher level than a Subnet).

        Args:
            node1: First node candidate.
            node2: Second node candidate.

        Returns:
            Tuple[Node, Node]: (Source, Target) ordered pair.
        """
        hierarchy = {
            "vpc": 10, "subnet": 9, "security_group": 8,
            "iam": 7, "kms": 6, "rds": 5, "db": 5,
            "instance": 4, "lambda": 3, "s3": 3,
        }

        def get_level(node: Node) -> int:
            name_lower = node.name.lower()
            for key, level in hierarchy.items():
                if key in name_lower:
                    return level
            return 0

        level1 = get_level(node1)
        level2 = get_level(node2)

        if level1 >= level2:
            return node1, node2
        return node2, node1


class Stitcher:
    """
    Orchestrator for cross-domain dependency stitching.

    The Stitcher manages the lifecycle of applying multiple `StitchingRule`s to a graph.
    It handles configuration, rule execution, and aggregation of results.

    Attributes:
        config (MatchConfig): Configuration for matching thresholds.
        rules (List[StitchingRule]): List of active rules to apply.
    """

    def __init__(self, config: Optional[MatchConfig] = None):
        """
        Initialize the Stitcher.

        Args:
            config: Optional match configuration. Uses defaults if None.
        """
        self.config = config or MatchConfig()
        self.rules: List[StitchingRule] = [
            EnvVarToInfraRule(self.config),
            InfraToInfraRule(self.config),
        ]
        self._last_results: Dict[str, List[Edge]] = {}

    def stitch(self, graph: DependencyGraph) -> List[Edge]:
        """
        Apply all configured stitching rules to the graph.

        Discovered edges are automatically added to the graph if they do not already exist.

        Args:
            graph: The dependency graph to update.

        Returns:
            List[Edge]: A list of all new edges created during this stitching session.
        """
        all_new_edges: List[Edge] = []
        self._last_results = {}

        for rule in self.rules:
            try:
                new_edges = rule.apply(graph)

                unique_edges = []
                for edge in new_edges:
                    if not graph.has_edge(edge.source_id, edge.target_id):
                        graph.add_edge(edge)
                        unique_edges.append(edge)

                self._last_results[rule.get_name()] = unique_edges
                all_new_edges.extend(unique_edges)

            except Exception as e:
                print(f"⚠️  Rule {rule.get_name()} failed: {e}")

        return all_new_edges
