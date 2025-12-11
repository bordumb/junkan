"""
Token Matching Utilities for jnkn.

Refactored to implement TokenMatcherProtocol for FFI readiness.
Includes robust filtering and overlap calculation logic.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import FrozenSet, List, Tuple

import yaml

from .interfaces import TokenMatcherProtocol

logger = logging.getLogger(__name__)


@dataclass
class TokenConfig:
    min_token_length: int = 3
    min_significant_tokens: int = 2
    blocked_tokens: FrozenSet[str] = field(default_factory=lambda: frozenset({
        "id", "db", "host", "url", "key", "name", "type", "data", "info",
        "config", "setting", "path", "port", "user", "password",
        "src", "dst", "in", "out", "err", "msg",
        "str", "int", "bool", "list", "dict"
    }))
    low_value_tokens: FrozenSet[str] = field(default_factory=lambda: frozenset({
        "aws", "gcp", "azure", "cloud", "main", "default", "prod", "dev",
        "instance", "cluster", "group", "pool", "bucket",
    }))
    low_value_weight: float = 0.5
    short_token_weight: float = 0.3

    def is_blocked(self, token: str) -> bool:
        return token.lower() in self.blocked_tokens

    def is_low_value(self, token: str) -> bool:
        return token.lower() in self.low_value_tokens


class TokenMatcher:
    """
    Pure Python implementation of TokenMatcherProtocol.
    """

    def __init__(self, config: TokenConfig | None = None):
        self.config = config or TokenConfig()

    def tokenize(self, name: str) -> List[str]:
        """
        Split a name into tokens.
        """
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":", " "]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]

    def get_significant_tokens(self, tokens: List[str]) -> List[str]:
        """
        Filter tokens to only significant ones.
        """
        significant = []
        for token in tokens:
            token_lower = token.lower()
            if self.config.is_blocked(token_lower):
                continue
            if len(token_lower) < self.config.min_token_length:
                continue
            significant.append(token_lower)
        return significant

    def calculate_overlap(
        self,
        tokens1: List[str],
        tokens2: List[str],
    ) -> Tuple[List[str], float]:
        """
        Calculate token overlap.
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
        
        This convenience method chains filtering and overlap calculation,
        restoring the API expected by the tests.
        """
        sig1 = self.get_significant_tokens(tokens1)
        sig2 = self.get_significant_tokens(tokens2)
        return self.calculate_overlap(sig1, sig2)

    # Additional helper methods specific to Python implementation
    def normalize(self, name: str) -> str:
        result = name.lower()
        for sep in ["_", ".", "-", "/", ":", " "]:
            result = result.replace(sep, "")
        return result


def load_config_from_yaml(path: Path) -> TokenConfig | None:
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
            blocked_tokens=frozenset(matching.get("blocked_tokens", [])) or TokenConfig().blocked_tokens,
            low_value_tokens=frozenset(matching.get("low_value_tokens", [])) or TokenConfig().low_value_tokens,
            low_value_weight=matching.get("low_value_weight", 0.5),
            short_token_weight=matching.get("short_token_weight", 0.3),
        )
    except Exception:
        return None


def create_default_matcher(config_path: Path | None = None) -> TokenMatcherProtocol:
    """
    Factory that returns an object satisfying TokenMatcherProtocol.
    Ideally, check a feature flag here to return Rust implementation later.
    """
    if config_path is None:
        config_path = Path(".jnkn/config.yaml")
    
    config = load_config_from_yaml(config_path)
    return TokenMatcher(config)
