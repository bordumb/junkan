"""
Confidence Calculation Engine.

This module provides the scoring logic for determining the likelihood that two
artifacts are related. It combines lexical analysis (token overlap, string matching)
with semantic heuristics (provider/consumer validation) to minimize false positives.
"""

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Dict, List, Set

from pydantic import BaseModel, ConfigDict, Field

from .types import NodeType

logger = logging.getLogger(__name__)


class ConfidenceSignal(StrEnum):
    """Positive indicators that increase confidence."""

    EXACT_MATCH = "exact_match"
    NORMALIZED_MATCH = "normalized_match"
    TOKEN_OVERLAP_HIGH = "token_overlap_high"
    TOKEN_OVERLAP_MEDIUM = "token_overlap_medium"
    SUFFIX_MATCH = "suffix_match"
    PREFIX_MATCH = "prefix_match"
    CONTAINS = "contains"
    SINGLE_TOKEN = "single_token"


class PenaltyType(StrEnum):
    """Negative indicators that reduce confidence."""

    SHORT_TOKEN = "short_token"
    COMMON_TOKEN = "common_token"
    AMBIGUITY = "ambiguity"
    LOW_VALUE_TOKEN = "low_value_token"
    GENERIC_MATCH = "generic_match"
    INVALID_DIRECTION = "invalid_direction"


@dataclass
class SignalResult:
    """Result of a single positive signal evaluation."""

    signal: ConfidenceSignal
    weight: float
    matched: bool
    details: str = ""
    matched_tokens: List[str] = field(default_factory=list)


@dataclass
class PenaltyResult:
    """Result of a single penalty evaluation."""

    penalty_type: PenaltyType
    multiplier: float
    reason: str = ""
    affected_tokens: List[str] = field(default_factory=list)


class ConfidenceResult(BaseModel):
    """
    Final result of a confidence calculation.
    """

    score: float = Field(ge=0.0, le=1.0)
    signals: List[Dict] = Field(default_factory=list)
    penalties: List[Dict] = Field(default_factory=list)
    explanation: str = ""
    matched_tokens: List[str] = Field(default_factory=list)
    source_node_id: str = ""
    target_node_id: str = ""

    model_config = ConfigDict(frozen=False)


class ConfidenceConfig(BaseModel):
    """
    Configuration for the confidence engine.
    """

    signal_weights: Dict[str, float] = Field(
        default_factory=lambda: {
            ConfidenceSignal.EXACT_MATCH: 1.0,
            ConfidenceSignal.NORMALIZED_MATCH: 0.9,
            ConfidenceSignal.TOKEN_OVERLAP_HIGH: 0.8,
            ConfidenceSignal.TOKEN_OVERLAP_MEDIUM: 0.6,
            ConfidenceSignal.SUFFIX_MATCH: 0.7,
            ConfidenceSignal.PREFIX_MATCH: 0.7,
            ConfidenceSignal.CONTAINS: 0.4,
            ConfidenceSignal.SINGLE_TOKEN: 0.2,
        }
    )

    penalty_multipliers: Dict[str, float] = Field(
        default_factory=lambda: {
            PenaltyType.SHORT_TOKEN: 0.5,
            PenaltyType.COMMON_TOKEN: 0.3,
            PenaltyType.AMBIGUITY: 0.8,
            PenaltyType.LOW_VALUE_TOKEN: 0.6,
            PenaltyType.GENERIC_MATCH: 0.1,
            PenaltyType.INVALID_DIRECTION: 0.1,
        }
    )

    short_token_length: int = 4
    min_token_overlap_high: int = 3
    min_token_overlap_medium: int = 2

    common_tokens: Set[str] = Field(
        default_factory=lambda: {
            "id",
            "name",
            "type",
            "key",
            "value",
            "data",
            "info",
            "config",
            "url",
            "uri",
            "path",
            "file",
            "dir",
            "host",
            "port",
            "user",
            "pass",
            "password",
            "token",
            "secret",
            "auth",
            "credential",
            "src",
            "dst",
            "in",
            "out",
            "new",
            "old",
            "temp",
            "tmp",
            "str",
            "int",
            "bool",
            "list",
            "dict",
            "obj",
            "item",
            "val",
            "db",
            "api",
            "app",
            "env",
            "var",
            "msg",
            "num",
        }
    )

    generic_terms: Set[str] = Field(
        default_factory=lambda: {
            "id",
            "uuid",
            "guid",
            "name",
            "created_at",
            "updated_at",
            "timestamp",
            "date",
            "time",
            "version",
            "status",
            "state",
            "type",
            "kind",
            "category",
            "class",
            "group",
            "owner",
            "description",
            "comment",
            "note",
            "text",
            "message",
            "error",
            "warning",
            "info",
            "debug",
            "trace",
        }
    )

    low_value_tokens: Set[str] = Field(
        default_factory=lambda: {
            "aws",
            "gcp",
            "azure",
            "k8s",
            "kubernetes",
            "docker",
            "prod",
            "production",
            "dev",
            "development",
            "staging",
            "test",
            "main",
            "master",
            "default",
            "primary",
            "secondary",
            "replica",
            "public",
            "private",
            "internal",
            "external",
            "local",
            "remote",
        }
    )

    model_config = ConfigDict(frozen=False)


class ConfidenceCalculator:
    """
    Engine for calculating match confidence scores.
    """

    def __init__(self, config: ConfidenceConfig | None = None):
        self.config = config or ConfidenceConfig()

    def _normalize(self, name: str) -> str:
        """Normalize name for comparison."""
        s = name.lower()
        for char in "._-/:":
            s = s.replace(char, "")
        return s

    def calculate(
        self,
        source_name: str,
        target_name: str,
        source_tokens: List[str],
        target_tokens: List[str],
        source_type: NodeType | None = None,
        target_type: NodeType | None = None,
        matched_tokens: List[str] | None = None,
        alternative_match_count: int = 0,
        source_node_id: str = "",
        target_node_id: str = "",
    ) -> ConfidenceResult:
        """Calculate confidence score."""
        if matched_tokens is None:
            source_set = set(source_tokens)
            target_set = set(target_tokens)
            matched_tokens = list(source_set & target_set)

        signal_results = self._evaluate_signals(
            source_name, target_name, source_tokens, target_tokens, matched_tokens
        )

        penalty_results = self._evaluate_penalties(
            source_name=source_name,
            target_name=target_name,
            matched_tokens=matched_tokens,
            alternative_match_count=alternative_match_count,
            source_type=source_type,
            target_type=target_type,
        )

        base_score = self._calculate_base_score(signal_results)
        final_score = self._apply_penalties(base_score, penalty_results)

        explanation = self._build_explanation(
            source_name, target_name, signal_results, penalty_results, base_score, final_score
        )

        return ConfidenceResult(
            score=final_score,
            signals=[self._signal_to_dict(s) for s in signal_results if s.matched],
            penalties=[self._penalty_to_dict(p) for p in penalty_results if p.multiplier < 1.0],
            explanation=explanation,
            matched_tokens=matched_tokens,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
        )

    def _evaluate_signals(
        self,
        source_name: str,
        target_name: str,
        source_tokens: List[str],
        target_tokens: List[str],
        matched_tokens: List[str],
    ) -> List[SignalResult]:
        """Evaluate positive matching signals."""
        results = []
        source_norm = self._normalize(source_name)
        target_norm = self._normalize(target_name)

        exact_match = source_name == target_name
        results.append(
            SignalResult(
                signal=ConfidenceSignal.EXACT_MATCH,
                weight=self.config.signal_weights[ConfidenceSignal.EXACT_MATCH],
                matched=exact_match,
                details=f"'{source_name}' == '{target_name}'",
            )
        )

        norm_match = source_norm == target_norm
        results.append(
            SignalResult(
                signal=ConfidenceSignal.NORMALIZED_MATCH,
                weight=self.config.signal_weights[ConfidenceSignal.NORMALIZED_MATCH],
                matched=norm_match and not exact_match,
                details=f"'{source_norm}' == '{target_norm}'",
            )
        )

        # Filter significant tokens for overlap calculation
        significant_tokens = [
            t
            for t in matched_tokens
            if t not in self.config.common_tokens and len(t) >= self.config.short_token_length
        ]

        high_overlap = len(significant_tokens) >= self.config.min_token_overlap_high
        results.append(
            SignalResult(
                signal=ConfidenceSignal.TOKEN_OVERLAP_HIGH,
                weight=self.config.signal_weights[ConfidenceSignal.TOKEN_OVERLAP_HIGH],
                matched=high_overlap,
                matched_tokens=significant_tokens,
            )
        )

        med_overlap = len(significant_tokens) >= self.config.min_token_overlap_medium
        results.append(
            SignalResult(
                signal=ConfidenceSignal.TOKEN_OVERLAP_MEDIUM,
                weight=self.config.signal_weights[ConfidenceSignal.TOKEN_OVERLAP_MEDIUM],
                matched=med_overlap and not high_overlap,
                matched_tokens=significant_tokens,
            )
        )

        min_len = 4
        suffix = (
            target_norm.endswith(source_norm) and len(source_norm) >= min_len and not norm_match
        )
        prefix = (
            target_norm.startswith(source_norm) and len(source_norm) >= min_len and not norm_match
        )
        contains = (
            source_norm in target_norm
            and len(source_norm) >= min_len
            and not norm_match
            and not suffix
            and not prefix
        )

        results.append(
            SignalResult(
                signal=ConfidenceSignal.SUFFIX_MATCH,
                weight=self.config.signal_weights[ConfidenceSignal.SUFFIX_MATCH],
                matched=suffix,
                details=f"Ends with '{source_norm}'",
            )
        )
        results.append(
            SignalResult(
                signal=ConfidenceSignal.PREFIX_MATCH,
                weight=self.config.signal_weights[ConfidenceSignal.PREFIX_MATCH],
                matched=prefix,
                details=f"Starts with '{source_norm}'",
            )
        )
        results.append(
            SignalResult(
                signal=ConfidenceSignal.CONTAINS,
                weight=self.config.signal_weights[ConfidenceSignal.CONTAINS],
                matched=contains,
                details=f"Contains '{source_norm}'",
            )
        )

        # Single Token Fallback
        any_structural = suffix or prefix or contains or norm_match or exact_match
        single_token = (
            len(matched_tokens) > 0 and not any_structural and not high_overlap and not med_overlap
        )

        results.append(
            SignalResult(
                signal=ConfidenceSignal.SINGLE_TOKEN,
                weight=self.config.signal_weights[ConfidenceSignal.SINGLE_TOKEN],
                matched=single_token,
                matched_tokens=matched_tokens,
            )
        )

        return results

    def _evaluate_penalties(
        self,
        source_name: str,
        target_name: str,
        matched_tokens: List[str],
        alternative_match_count: int,
        source_type: NodeType | None,
        target_type: NodeType | None,
    ) -> List[PenaltyResult]:
        """Evaluate negative penalties."""
        results = []
        source_norm = self._normalize(source_name)

        if source_norm in self.config.generic_terms:
            results.append(
                PenaltyResult(
                    penalty_type=PenaltyType.GENERIC_MATCH,
                    multiplier=self.config.penalty_multipliers[PenaltyType.GENERIC_MATCH],
                    reason=f"Source '{source_name}' is a generic term",
                )
            )

        if source_type and target_type:
            if not self._is_valid_direction(source_type, target_type):
                results.append(
                    PenaltyResult(
                        penalty_type=PenaltyType.INVALID_DIRECTION,
                        multiplier=self.config.penalty_multipliers[PenaltyType.INVALID_DIRECTION],
                        reason=f"Invalid flow: {source_type.value} -> {target_type.value}",
                    )
                )

        common_found = [t for t in matched_tokens if t in self.config.common_tokens]
        non_common_found = [t for t in matched_tokens if t not in self.config.common_tokens]
        if common_found and not non_common_found:
            results.append(
                PenaltyResult(
                    penalty_type=PenaltyType.COMMON_TOKEN,
                    multiplier=self.config.penalty_multipliers[PenaltyType.COMMON_TOKEN],
                    reason="All matched tokens are common words",
                    affected_tokens=common_found,
                )
            )

        # Modified Short Token Logic: Only penalize if ALL matched tokens are short
        short_tokens = [t for t in matched_tokens if len(t) < self.config.short_token_length]
        long_tokens = [t for t in matched_tokens if len(t) >= self.config.short_token_length]

        if short_tokens and not long_tokens:
            results.append(
                PenaltyResult(
                    penalty_type=PenaltyType.SHORT_TOKEN,
                    multiplier=self.config.penalty_multipliers[PenaltyType.SHORT_TOKEN],
                    reason=f"All matched tokens are short (<{self.config.short_token_length})",
                    affected_tokens=short_tokens,
                )
            )

        if alternative_match_count > 1:
            raw_penalty = self.config.penalty_multipliers[PenaltyType.AMBIGUITY]
            multiplier = max(0.2, raw_penalty ** (alternative_match_count - 1))
            results.append(
                PenaltyResult(
                    penalty_type=PenaltyType.AMBIGUITY,
                    multiplier=multiplier,
                    reason=f"Matched {alternative_match_count} distinct targets",
                )
            )

        low_value = [t for t in matched_tokens if t in self.config.low_value_tokens]
        if low_value and len(low_value) >= len(non_common_found):
            results.append(
                PenaltyResult(
                    penalty_type=PenaltyType.LOW_VALUE_TOKEN,
                    multiplier=self.config.penalty_multipliers[PenaltyType.LOW_VALUE_TOKEN],
                    reason="Match dominated by low-value tokens",
                    affected_tokens=low_value,
                )
            )

        return results

    def _is_valid_direction(self, source: NodeType, target: NodeType) -> bool:
        valid_pairs = {
            (NodeType.INFRA_RESOURCE, NodeType.ENV_VAR),
            (NodeType.CONFIG_KEY, NodeType.ENV_VAR),
            (NodeType.SECRET, NodeType.ENV_VAR),
            (NodeType.INFRA_RESOURCE, NodeType.INFRA_RESOURCE),
            (NodeType.DATA_ASSET, NodeType.CODE_FILE),
            (NodeType.DATA_ASSET, NodeType.CODE_ENTITY),
            (NodeType.CODE_FILE, NodeType.CODE_ENTITY),
        }
        if (source, target) in valid_pairs:
            return True
        if source == NodeType.ENV_VAR and target == NodeType.INFRA_RESOURCE:
            return False
        return True

    def _calculate_base_score(self, signals: List[SignalResult]) -> float:
        matched_weights = [s.weight for s in signals if s.matched]
        if not matched_weights:
            return 0.0
        max_weight = max(matched_weights)
        bonus = min(0.1, (len(matched_weights) - 1) * 0.02)
        return min(1.0, max_weight + bonus)

    def _apply_penalties(self, score: float, penalties: List[PenaltyResult]) -> float:
        final = score
        for p in penalties:
            final *= p.multiplier
        return round(final, 4)

    def _build_explanation(self, source, target, signals, penalties, base, final) -> str:
        lines = [f"Match: {source} -> {target}", f"Base Confidence: {base:.2f}"]
        matched_sigs = [s for s in signals if s.matched]
        if matched_sigs:
            lines.append("Signals:")
            for s in matched_sigs:
                details = f" ({s.details})" if s.details else ""
                lines.append(f"  + {s.signal.value} ({s.weight:.2f}){details}")
        if penalties:
            lines.append("Penalties:")
            for p in penalties:
                lines.append(f"  - {p.penalty_type.value} (x{p.multiplier:.2f}): {p.reason}")
        lines.append(f"Final Score: {final:.2f}")
        return "\n".join(lines)

    @staticmethod
    def _signal_to_dict(s: SignalResult) -> Dict:
        return {
            "signal": s.signal.value,
            "weight": s.weight,
            "matched": s.matched,
            "details": s.details,
            "matched_tokens": s.matched_tokens,
        }

    @staticmethod
    def _penalty_to_dict(p: PenaltyResult) -> Dict:
        return {
            "penalty_type": p.penalty_type.value,
            "multiplier": p.multiplier,
            "reason": p.reason,
            "affected_tokens": p.affected_tokens,
        }


def create_default_calculator() -> ConfidenceCalculator:
    return ConfidenceCalculator()
