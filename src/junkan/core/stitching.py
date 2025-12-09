"""
Cross-domain dependency stitching.

This module implements the core "glue" logic that connects disparate domains:
- Environment variables to infrastructure resources
- Code references to data assets
- Configuration keys to their providers

Key Design Principles:
1. Multiple matching strategies with confidence scoring
2. Token-based indexing for O(n) instead of O(n*m) matching
3. Configurable thresholds to filter low-confidence matches
4. Explainable results for debugging false positives
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Set, Optional, Tuple, Any
from collections import defaultdict
from .graph import DependencyGraph
from .types import (
    Node, Edge, NodeType, RelationshipType,
    MatchStrategy, MatchResult
)


class MatchConfig:
    """
    Configuration for matching behavior.
    
    Allows tuning of confidence thresholds and strategy weights.
    """
    
    def __init__(
        self,
        min_confidence: float = 0.5,
        min_token_overlap: int = 2,
        min_token_length: int = 2,
        strategy_weights: Optional[Dict[MatchStrategy, float]] = None,
    ):
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
    """
    
    @staticmethod
    def normalize(name: str) -> str:
        """Normalize a name by lowercasing and removing separators."""
        result = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            result = result.replace(sep, "")
        return result
    
    @staticmethod
    def tokenize(name: str) -> List[str]:
        """Split a name into tokens."""
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]
    
    @staticmethod
    def token_overlap(
        tokens1: List[str], tokens2: List[str]
    ) -> Tuple[List[str], float]:
        """
        Calculate token overlap between two token lists.
        
        Returns:
            Tuple of (overlapping tokens, Jaccard similarity score)
        """
        set1 = set(tokens1)
        set2 = set(tokens2)
        overlap = set1 & set2
        union = set1 | set2
        
        if not union:
            return [], 0.0
        
        jaccard = len(overlap) / len(union)
        return list(overlap), jaccard
    
    @staticmethod
    def significant_token_overlap(
        tokens1: List[str],
        tokens2: List[str],
        min_length: int = 2
    ) -> Tuple[List[str], float]:
        """
        Calculate overlap only for significant (long enough) tokens.
        """
        sig1 = [t for t in tokens1 if len(t) >= min_length]
        sig2 = [t for t in tokens2 if len(t) >= min_length]
        return TokenMatcher.token_overlap(sig1, sig2)


class StitchingRule(ABC):
    """
    Abstract base class for stitching rules.
    """
    
    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()
    
    @abstractmethod
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        """Apply this rule to discover new edges."""
        pass
    
    @abstractmethod
    def get_name(self) -> str:
        """Return a descriptive name for this rule."""
        pass


class EnvVarToInfraRule(StitchingRule):
    """
    Links environment variables to infrastructure resources.
    
    Matching Strategies (in order of confidence):
    1. NORMALIZED: "PAYMENT_DB_HOST" normalized matches "payment_db_host"
    2. TOKEN_OVERLAP: Shared significant tokens (payment, db, host)
    3. SUFFIX: Env var name is suffix of infra name
    
    Uses token index for O(n) performance instead of O(n*m).
    """
    
    def get_name(self) -> str:
        return "EnvVarToInfraRule"
    
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        edges = []
        
        # Get all env var nodes (check both ENV_VAR and DATA_ASSET with env: prefix)
        env_nodes = graph.get_nodes_by_type(NodeType.ENV_VAR)
        if not env_nodes:
            env_nodes = [
                n for n in graph.get_nodes_by_type(NodeType.DATA_ASSET)
                if n.id.startswith("env:")
            ]
        
        # Get all infra nodes
        infra_nodes = graph.get_nodes_by_type(NodeType.INFRA_RESOURCE)
        
        if not env_nodes or not infra_nodes:
            return edges
        
        # Build lookup structures for infra nodes - O(m)
        infra_by_normalized: Dict[str, List[Node]] = defaultdict(list)
        infra_by_tokens: Dict[str, List[Node]] = defaultdict(list)
        
        for infra in infra_nodes:
            normalized = TokenMatcher.normalize(infra.name)
            infra_by_normalized[normalized].append(infra)
            
            tokens = infra.tokens or TokenMatcher.tokenize(infra.name)
            for token in tokens:
                if len(token) >= self.config.min_token_length:
                    infra_by_tokens[token].append(infra)
        
        # Match each env var - O(n) with index lookups
        for env in env_nodes:
            env_normalized = TokenMatcher.normalize(env.name)
            env_tokens = env.tokens or TokenMatcher.tokenize(env.name)
            
            best_matches: Dict[str, MatchResult] = {}
            
            # Strategy 1: Exact normalized match
            for infra in infra_by_normalized.get(env_normalized, []):
                match = MatchResult(
                    source_node=env.id,
                    target_node=infra.id,
                    strategy=MatchStrategy.NORMALIZED,
                    confidence=self.config.strategy_weights[MatchStrategy.NORMALIZED],
                    matched_tokens=env_tokens,
                    explanation=f"Normalized match: '{env.name}' == '{infra.name}'"
                )
                self._update_best_match(best_matches, infra.id, match)
            
            # Strategy 2: Token overlap (using index)
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
                        source_node=env.id,
                        target_node=infra.id,
                        strategy=MatchStrategy.TOKEN_OVERLAP,
                        confidence=confidence,
                        matched_tokens=overlap,
                        explanation=f"Token overlap: {overlap} (score: {score:.2f})"
                    )
                    self._update_best_match(best_matches, infra_id, match)
            
            # Strategy 3: Suffix matching
            if len(env_normalized) >= 4:
                for normalized_infra, infra_list in infra_by_normalized.items():
                    if normalized_infra.endswith(env_normalized):
                        for infra in infra_list:
                            match = MatchResult(
                                source_node=env.id,
                                target_node=infra.id,
                                strategy=MatchStrategy.SUFFIX,
                                confidence=self.config.strategy_weights[MatchStrategy.SUFFIX],
                                matched_tokens=env_tokens,
                                explanation=f"Suffix: '{infra.name}' ends with '{env.name}'"
                            )
                            self._update_best_match(best_matches, infra.id, match)
            
            # Create edges for matches above threshold
            for infra_id, match in best_matches.items():
                if match.confidence >= self.config.min_confidence:
                    edges.append(Edge(
                        source_id=env.id,
                        target_id=infra_id,
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
        """Keep only the highest-confidence match for each target."""
        if target_id not in best_matches:
            best_matches[target_id] = new_match
        elif new_match.confidence > best_matches[target_id].confidence:
            best_matches[target_id] = new_match


class InfraToInfraRule(StitchingRule):
    """
    Links infrastructure resources based on naming conventions.
    """
    
    def get_name(self) -> str:
        return "InfraToInfraRule"
    
    def apply(self, graph: DependencyGraph) -> List[Edge]:
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
        """Determine edge direction based on resource type hierarchy."""
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
    Orchestrates cross-domain dependency stitching.
    
    Features:
    - Configurable rule set
    - Confidence thresholds
    - Deduplication of edges
    - Statistics and reporting
    """
    
    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()
        self.rules: List[StitchingRule] = [
            EnvVarToInfraRule(self.config),
            InfraToInfraRule(self.config),
        ]
        self._last_results: Dict[str, List[Edge]] = {}
    
    def add_rule(self, rule: StitchingRule) -> None:
        """Add a custom stitching rule."""
        self.rules.append(rule)
    
    def stitch(self, graph: DependencyGraph) -> List[Edge]:
        """
        Apply all stitching rules and add discovered edges to the graph.
        
        Returns:
            List of all newly created edges (for persistence)
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
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics from the last stitch operation."""
        return {
            "total_edges_created": sum(
                len(edges) for edges in self._last_results.values()
            ),
            "edges_by_rule": {
                rule: len(edges) for rule, edges in self._last_results.items()
            },
            "confidence_distribution": self._confidence_distribution(),
        }
    
    def _confidence_distribution(self) -> Dict[str, int]:
        """Calculate distribution of confidence scores."""
        buckets = {"high (>0.8)": 0, "medium (0.6-0.8)": 0, "low (<0.6)": 0}
        
        for edges in self._last_results.values():
            for edge in edges:
                if edge.confidence > 0.8:
                    buckets["high (>0.8)"] += 1
                elif edge.confidence >= 0.6:
                    buckets["medium (0.6-0.8)"] += 1
                else:
                    buckets["low (<0.6)"] += 1
        
        return buckets