"""
Token Matching Utilities for jnkn.

This module provides utilities for token-based matching with:
- Minimum token length filtering
- Blocked token exclusion
- Low-value token weighting
- Configurable matching behavior

The TokenMatcher class is the central component for all token-based
operations in the stitching system.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Tuple

import yaml

logger = logging.getLogger(__name__)


@dataclass
class TokenConfig:
    """
    Configuration for token matching behavior.

    Controls which tokens are considered significant for matching
    and how they contribute to confidence scores.
    """

    # Minimum length for a token to be considered
    min_token_length: int = 3

    # Minimum significant tokens required for a match
    min_significant_tokens: int = 2

    # Tokens that provide no signal and should be ignored
    blocked_tokens: FrozenSet[str] = field(
        default_factory=lambda: frozenset(
            {
                # Generic identifiers
                "id",
                "db",
                "host",
                "url",
                "key",
                "name",
                "type",
                "data",
                "info",
                "temp",
                "test",
                "api",
                "app",
                "env",
                "var",
                "val",
                # Configuration terms
                "config",
                "setting",
                "path",
                "port",
                "user",
                "password",
                "secret",
                "token",
                "auth",
                "log",
                "file",
                "dir",
                # Source/destination
                "src",
                "dst",
                "in",
                "out",
                "err",
                "msg",
                # Type hints
                "str",
                "int",
                "num",
                "bool",
                "list",
                "dict",
                "map",
                # Very short common words
                "the",
                "and",
                "for",
                "not",
                "get",
                "set",
                "new",
                "old",
            }
        )
    )

    # Tokens that provide weak signal (0.5x weight)
    low_value_tokens: FrozenSet[str] = field(
        default_factory=lambda: frozenset(
            {
                # Cloud providers
                "aws",
                "gcp",
                "azure",
                "cloud",
                # Environment names
                "main",
                "default",
                "primary",
                "secondary",
                "production",
                "prod",
                "staging",
                "stage",
                "dev",
                "development",
                "internal",
                "external",
                "public",
                "private",
                "local",
                "remote",
                # Common modifiers
                "master",
                "slave",
                "read",
                "write",
                "replica",
                "backup",
                "cache",
                "queue",
                "worker",
                "service",
                # Common resource types that don't differentiate
                "instance",
                "cluster",
                "group",
                "pool",
                "bucket",
            }
        )
    )

    # Weight multiplier for low-value tokens
    low_value_weight: float = 0.5

    # Weight multiplier for short tokens (< min_token_length)
    short_token_weight: float = 0.3

    def is_blocked(self, token: str) -> bool:
        """Check if a token is blocked."""
        return token.lower() in self.blocked_tokens

    def is_low_value(self, token: str) -> bool:
        """Check if a token is low-value."""
        return token.lower() in self.low_value_tokens

    def is_short(self, token: str) -> bool:
        """Check if a token is too short."""
        return len(token) < self.min_token_length

    def get_token_weight(self, token: str) -> float:
        """
        Get the weight multiplier for a token.

        Returns:
            1.0 for normal tokens
            0.0 for blocked tokens
            0.5 for low-value tokens
            0.3 for short tokens
            Compounds if multiple conditions apply
        """
        if self.is_blocked(token):
            return 0.0

        weight = 1.0

        if self.is_low_value(token):
            weight *= self.low_value_weight

        if self.is_short(token):
            weight *= self.short_token_weight

        return weight


class TokenMatcher:
    """
    Token-based matching with configurable filtering.

    Usage:
        matcher = TokenMatcher()

        # Tokenize names
        tokens1 = matcher.tokenize("PAYMENT_DB_HOST")
        tokens2 = matcher.tokenize("payment_database_host")

        # Get significant tokens only
        sig1 = matcher.get_significant_tokens(tokens1)
        sig2 = matcher.get_significant_tokens(tokens2)

        # Calculate overlap
        overlap, score = matcher.calculate_overlap(sig1, sig2)
    """

    def __init__(self, config: TokenConfig | None = None):
        """
        Initialize the token matcher.

        Args:
            config: Optional TokenConfig. Uses defaults if not provided.
        """
        self.config = config or TokenConfig()

    @staticmethod
    def normalize(name: str) -> str:
        """
        Normalize a name by lowercasing and removing separators.

        Args:
            name: Name to normalize

        Returns:
            Normalized string (e.g., "PAYMENT_DB_HOST" -> "paymentdbhost")
        """
        result = name.lower()
        for sep in ["_", ".", "-", "/", ":", " "]:
            result = result.replace(sep, "")
        return result

    @staticmethod
    def tokenize(name: str) -> List[str]:
        """
        Split a name into tokens.

        Args:
            name: Name to tokenize

        Returns:
            List of lowercase tokens (e.g., "PAYMENT_DB_HOST" -> ["payment", "db", "host"])
        """
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":", " "]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]

    def get_significant_tokens(self, tokens: List[str]) -> List[str]:
        """
        Filter tokens to only significant ones.

        Removes blocked tokens and those below minimum length.

        Args:
            tokens: List of tokens

        Returns:
            List of significant tokens
        """
        significant = []
        for token in tokens:
            token_lower = token.lower()

            # Skip blocked tokens
            if self.config.is_blocked(token_lower):
                continue

            # Skip tokens that are too short
            if len(token_lower) < self.config.min_token_length:
                continue

            significant.append(token_lower)

        return significant

    def get_weighted_tokens(self, tokens: List[str]) -> List[Tuple[str, float]]:
        """
        Get tokens with their weight multipliers.

        Args:
            tokens: List of tokens

        Returns:
            List of (token, weight) tuples
        """
        weighted = []
        for token in tokens:
            token_lower = token.lower()
            weight = self.config.get_token_weight(token_lower)

            if weight > 0:
                weighted.append((token_lower, weight))

        return weighted

    def calculate_overlap(
        self,
        tokens1: List[str],
        tokens2: List[str],
    ) -> Tuple[List[str], float]:
        """
        Calculate token overlap between two token lists.

        Args:
            tokens1: First token list
            tokens2: Second token list

        Returns:
            Tuple of (overlapping tokens, Jaccard similarity score)
        """
        set1 = set(t.lower() for t in tokens1)
        set2 = set(t.lower() for t in tokens2)

        overlap = set1 & set2
        union = set1 | set2

        if not union:
            return [], 0.0

        jaccard = len(overlap) / len(union)
        return list(overlap), jaccard

    def calculate_significant_overlap(
        self,
        tokens1: List[str],
        tokens2: List[str],
    ) -> Tuple[List[str], float]:
        """
        Calculate overlap using only significant tokens.

        Args:
            tokens1: First token list
            tokens2: Second token list

        Returns:
            Tuple of (overlapping significant tokens, Jaccard similarity score)
        """
        sig1 = self.get_significant_tokens(tokens1)
        sig2 = self.get_significant_tokens(tokens2)

        return self.calculate_overlap(sig1, sig2)

    def calculate_weighted_overlap(
        self,
        tokens1: List[str],
        tokens2: List[str],
    ) -> Tuple[List[str], float]:
        """
        Calculate overlap with weighted scoring.

        Low-value and short tokens contribute less to the score.

        Args:
            tokens1: First token list
            tokens2: Second token list

        Returns:
            Tuple of (overlapping tokens, weighted score)
        """
        weighted1 = dict(self.get_weighted_tokens(tokens1))
        weighted2 = dict(self.get_weighted_tokens(tokens2))

        # Find overlapping tokens
        overlap_tokens = set(weighted1.keys()) & set(weighted2.keys())

        if not overlap_tokens:
            return [], 0.0

        # Calculate weighted overlap score
        overlap_weight = sum(min(weighted1[t], weighted2[t]) for t in overlap_tokens)

        total_weight = sum(weighted1.values()) + sum(weighted2.values()) - overlap_weight

        if total_weight == 0:
            return list(overlap_tokens), 0.0

        score = overlap_weight / total_weight
        return list(overlap_tokens), score

    def has_sufficient_overlap(
        self,
        tokens1: List[str],
        tokens2: List[str],
    ) -> bool:
        """
        Check if two token lists have sufficient overlap for matching.

        Uses min_significant_tokens from config.

        Args:
            tokens1: First token list
            tokens2: Second token list

        Returns:
            True if overlap is sufficient
        """
        overlap, _ = self.calculate_significant_overlap(tokens1, tokens2)
        return len(overlap) >= self.config.min_significant_tokens

    def get_match_quality(
        self,
        source_tokens: List[str],
        target_tokens: List[str],
    ) -> Dict[str, any]:
        """
        Get detailed match quality information.

        Args:
            source_tokens: Source token list
            target_tokens: Target token list

        Returns:
            Dictionary with match details
        """
        # Get significant tokens
        sig_source = self.get_significant_tokens(source_tokens)
        sig_target = self.get_significant_tokens(target_tokens)

        # Calculate overlaps
        overlap, jaccard = self.calculate_overlap(sig_source, sig_target)
        _, weighted_score = self.calculate_weighted_overlap(source_tokens, target_tokens)

        # Find blocked and low-value tokens
        blocked_source = [t for t in source_tokens if self.config.is_blocked(t.lower())]
        blocked_target = [t for t in target_tokens if self.config.is_blocked(t.lower())]

        low_value_source = [t for t in source_tokens if self.config.is_low_value(t.lower())]
        low_value_target = [t for t in target_tokens if self.config.is_low_value(t.lower())]

        return {
            "source_tokens": source_tokens,
            "target_tokens": target_tokens,
            "significant_source": sig_source,
            "significant_target": sig_target,
            "overlap": overlap,
            "overlap_count": len(overlap),
            "jaccard_score": jaccard,
            "weighted_score": weighted_score,
            "blocked_source": blocked_source,
            "blocked_target": blocked_target,
            "low_value_source": low_value_source,
            "low_value_target": low_value_target,
            "sufficient": len(overlap) >= self.config.min_significant_tokens,
        }


def load_config_from_yaml(path: Path) -> TokenConfig | None:
    """
    Load TokenConfig from a YAML configuration file.

    Expected format:
        matching:
          min_token_length: 3
          min_significant_tokens: 2
          blocked_tokens:
            - id
            - db
            - host
          low_value_tokens:
            - aws
            - main

    Args:
        path: Path to YAML file

    Returns:
        TokenConfig if file exists and is valid, None otherwise
    """
    if not path.exists():
        return None

    try:
        with open(path) as f:
            data = yaml.safe_load(f)

        if not data or "matching" not in data:
            return None

        matching = data["matching"]

        return TokenConfig(
            min_token_length=matching.get("min_token_length", 3),
            min_significant_tokens=matching.get("min_significant_tokens", 2),
            blocked_tokens=frozenset(matching.get("blocked_tokens", []))
            or TokenConfig().blocked_tokens,
            low_value_tokens=frozenset(matching.get("low_value_tokens", []))
            or TokenConfig().low_value_tokens,
            low_value_weight=matching.get("low_value_weight", 0.5),
            short_token_weight=matching.get("short_token_weight", 0.3),
        )

    except Exception as e:
        logger.warning(f"Failed to load token config from {path}: {e}")
        return None


def create_default_matcher(config_path: Path | None = None) -> TokenMatcher:
    """
    Create a TokenMatcher with configuration from file or defaults.

    Args:
        config_path: Optional path to config file.
                    Defaults to .jnkn/config.yaml

    Returns:
        Configured TokenMatcher
    """
    if config_path is None:
        config_path = Path(".jnkn/config.yaml")

    config = load_config_from_yaml(config_path)
    return TokenMatcher(config)


# Convenience functions for static access
def normalize(name: str) -> str:
    """Normalize a name. See TokenMatcher.normalize."""
    return TokenMatcher.normalize(name)


def tokenize(name: str) -> List[str]:
    """Tokenize a name. See TokenMatcher.tokenize."""
    return TokenMatcher.tokenize(name)
