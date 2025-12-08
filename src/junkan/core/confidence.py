"""
Confidence Calculation Engine for Junkan.

This module provides a sophisticated confidence scoring system for dependency matches.
It combines multiple signals (exact match, token overlap, suffix/prefix match, etc.)
with configurable weights and penalty factors to produce explainable confidence scores.

Key Features:
- Multiple confidence signals with configurable weights
- Penalty factors for short tokens, common tokens, and ambiguous matches
- Human-readable explanations for all matches
- Extensible architecture for custom signals

Design Principles:
- False positives are worse than false negatives
- Every match must have an explainable confidence score
- Penalties reduce confidence, never increase it
"""

from enum import StrEnum, auto
from typing import List, Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


class ConfidenceSignal(StrEnum):
    """
    Signals that contribute to match confidence.
    
    Each signal represents a type of evidence that two items are related.
    Higher weights indicate stronger evidence.
    """
    EXACT_MATCH = "exact_match"
    NORMALIZED_MATCH = "normalized_match"
    TOKEN_OVERLAP_HIGH = "token_overlap_high"  # 3+ tokens
    TOKEN_OVERLAP_MEDIUM = "token_overlap_medium"  # 2 tokens
    SUFFIX_MATCH = "suffix_match"
    PREFIX_MATCH = "prefix_match"
    CONTAINS = "contains"
    SINGLE_TOKEN = "single_token"


class PenaltyType(StrEnum):
    """
    Penalty types that reduce match confidence.
    
    Penalties are applied multiplicatively to reduce confidence
    for potentially unreliable matches.
    """
    SHORT_TOKEN = "short_token"
    COMMON_TOKEN = "common_token"
    AMBIGUITY = "ambiguity"
    LOW_VALUE_TOKEN = "low_value_token"


@dataclass
class SignalResult:
    """Result of evaluating a single confidence signal."""
    signal: ConfidenceSignal
    weight: float
    matched: bool
    details: str = ""
    matched_tokens: List[str] = field(default_factory=list)


@dataclass
class PenaltyResult:
    """Result of evaluating a single penalty."""
    penalty_type: PenaltyType
    multiplier: float  # 0.0 to 1.0, applied multiplicatively
    reason: str = ""
    affected_tokens: List[str] = field(default_factory=list)


class ConfidenceResult(BaseModel):
    """
    Complete result of confidence calculation.
    
    Contains the final score, all contributing signals, applied penalties,
    and a human-readable explanation.
    """
    score: float = Field(ge=0.0, le=1.0)
    signals: List[Dict] = Field(default_factory=list)  # SignalResult as dicts
    penalties: List[Dict] = Field(default_factory=list)  # PenaltyResult as dicts
    explanation: str = ""
    matched_tokens: List[str] = Field(default_factory=list)
    source_node_id: str = ""
    target_node_id: str = ""
    
    class Config:
        frozen = False


class ConfidenceConfig(BaseModel):
    """
    Configuration for confidence calculation.
    
    Allows customization of signal weights, penalty factors, and thresholds.
    """
    # Signal weights (0.0 to 1.0)
    signal_weights: Dict[str, float] = Field(default_factory=lambda: {
        ConfidenceSignal.EXACT_MATCH: 1.0,
        ConfidenceSignal.NORMALIZED_MATCH: 0.9,
        ConfidenceSignal.TOKEN_OVERLAP_HIGH: 0.8,
        ConfidenceSignal.TOKEN_OVERLAP_MEDIUM: 0.6,
        ConfidenceSignal.SUFFIX_MATCH: 0.7,
        ConfidenceSignal.PREFIX_MATCH: 0.7,
        ConfidenceSignal.CONTAINS: 0.4,
        ConfidenceSignal.SINGLE_TOKEN: 0.2,
    })
    
    # Penalty multipliers (0.0 to 1.0, lower = stronger penalty)
    penalty_multipliers: Dict[str, float] = Field(default_factory=lambda: {
        PenaltyType.SHORT_TOKEN: 0.5,
        PenaltyType.COMMON_TOKEN: 0.7,
        PenaltyType.AMBIGUITY: 0.8,
        PenaltyType.LOW_VALUE_TOKEN: 0.6,
    })
    
    # Thresholds
    short_token_length: int = 4  # Tokens shorter than this get penalty
    min_token_overlap_high: int = 3  # Minimum for "high" overlap
    min_token_overlap_medium: int = 2  # Minimum for "medium" overlap
    
    # Common tokens that provide weak signal
    common_tokens: Set[str] = Field(default_factory=lambda: {
        "id", "db", "host", "url", "key", "name", "type", "data",
        "info", "temp", "test", "api", "app", "env", "var", "val",
        "config", "setting", "path", "port", "user", "password",
        "secret", "token", "auth", "log", "file", "dir", "src",
        "dst", "in", "out", "err", "msg", "str", "int", "num",
    })
    
    # Low-value tokens (provide some signal but reduced)
    low_value_tokens: Set[str] = Field(default_factory=lambda: {
        "aws", "gcp", "azure", "main", "default", "primary",
        "production", "prod", "staging", "dev", "development",
        "internal", "external", "public", "private", "local",
        "remote", "master", "slave", "read", "write",
    })

    class Config:
        frozen = False


class ConfidenceCalculator:
    """
    Calculate confidence scores for dependency matches.
    
    Combines multiple signals with configurable weights and penalty factors
    to produce explainable confidence scores.
    
    Usage:
        calculator = ConfidenceCalculator()
        result = calculator.calculate(source_node, target_node, matched_tokens)
        print(calculator.explain(result))
    """
    
    def __init__(self, config: Optional[ConfidenceConfig] = None):
        """
        Initialize the confidence calculator.
        
        Args:
            config: Optional configuration. Uses defaults if not provided.
        """
        self.config = config or ConfidenceConfig()
    
    def calculate(
        self,
        source_name: str,
        target_name: str,
        source_tokens: List[str],
        target_tokens: List[str],
        matched_tokens: Optional[List[str]] = None,
        alternative_match_count: int = 0,
        source_node_id: str = "",
        target_node_id: str = "",
    ) -> ConfidenceResult:
        """
        Calculate confidence score for a match between source and target.
        
        Args:
            source_name: Name of the source node (e.g., "PAYMENT_DB_HOST")
            target_name: Name of the target node (e.g., "payment_db_host")
            source_tokens: Tokenized source name
            target_tokens: Tokenized target name
            matched_tokens: Pre-computed matched tokens (optional)
            alternative_match_count: Number of other potential matches for source
            source_node_id: ID of source node for reference
            target_node_id: ID of target node for reference
        
        Returns:
            ConfidenceResult with score, signals, penalties, and explanation
        """
        # Calculate matched tokens if not provided
        if matched_tokens is None:
            source_set = set(source_tokens)
            target_set = set(target_tokens)
            matched_tokens = list(source_set & target_set)
        
        # Evaluate all signals
        signal_results = self._evaluate_signals(
            source_name, target_name,
            source_tokens, target_tokens,
            matched_tokens
        )
        
        # Evaluate penalties
        penalty_results = self._evaluate_penalties(
            matched_tokens, alternative_match_count
        )
        
        # Calculate base score from signals
        base_score = self._calculate_base_score(signal_results)
        
        # Apply penalties
        final_score = self._apply_penalties(base_score, penalty_results)
        
        # Build explanation
        explanation = self._build_explanation(
            source_name, target_name,
            signal_results, penalty_results,
            base_score, final_score
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
        """Evaluate all confidence signals."""
        results = []
        
        # Signal 1: Exact match
        exact_match = source_name == target_name
        results.append(SignalResult(
            signal=ConfidenceSignal.EXACT_MATCH,
            weight=self.config.signal_weights[ConfidenceSignal.EXACT_MATCH],
            matched=exact_match,
            details=f"'{source_name}' == '{target_name}'" if exact_match else "",
        ))
        
        # Signal 2: Normalized match
        source_normalized = self._normalize(source_name)
        target_normalized = self._normalize(target_name)
        normalized_match = source_normalized == target_normalized
        results.append(SignalResult(
            signal=ConfidenceSignal.NORMALIZED_MATCH,
            weight=self.config.signal_weights[ConfidenceSignal.NORMALIZED_MATCH],
            matched=normalized_match and not exact_match,  # Don't double count
            details=f"'{source_normalized}' == '{target_normalized}'" if normalized_match else "",
        ))
        
        # Signal 3 & 4: Token overlap (high vs medium)
        overlap_count = len(matched_tokens)
        significant_overlap = [t for t in matched_tokens 
                             if t not in self.config.common_tokens
                             and len(t) >= self.config.short_token_length]
        
        high_overlap = len(significant_overlap) >= self.config.min_token_overlap_high
        medium_overlap = len(significant_overlap) >= self.config.min_token_overlap_medium
        
        results.append(SignalResult(
            signal=ConfidenceSignal.TOKEN_OVERLAP_HIGH,
            weight=self.config.signal_weights[ConfidenceSignal.TOKEN_OVERLAP_HIGH],
            matched=high_overlap,
            details=f"{len(significant_overlap)} significant tokens: {significant_overlap}" if high_overlap else "",
            matched_tokens=significant_overlap if high_overlap else [],
        ))
        
        results.append(SignalResult(
            signal=ConfidenceSignal.TOKEN_OVERLAP_MEDIUM,
            weight=self.config.signal_weights[ConfidenceSignal.TOKEN_OVERLAP_MEDIUM],
            matched=medium_overlap and not high_overlap,  # Don't double count
            details=f"{len(significant_overlap)} significant tokens: {significant_overlap}" if medium_overlap and not high_overlap else "",
            matched_tokens=significant_overlap if medium_overlap and not high_overlap else [],
        ))
        
        # Signal 5: Suffix match
        suffix_match = (target_normalized.endswith(source_normalized) and 
                       len(source_normalized) >= 4 and
                       not normalized_match)
        results.append(SignalResult(
            signal=ConfidenceSignal.SUFFIX_MATCH,
            weight=self.config.signal_weights[ConfidenceSignal.SUFFIX_MATCH],
            matched=suffix_match,
            details=f"'{target_normalized}' ends with '{source_normalized}'" if suffix_match else "",
        ))
        
        # Signal 6: Prefix match
        prefix_match = (target_normalized.startswith(source_normalized) and 
                       len(source_normalized) >= 4 and
                       not normalized_match)
        results.append(SignalResult(
            signal=ConfidenceSignal.PREFIX_MATCH,
            weight=self.config.signal_weights[ConfidenceSignal.PREFIX_MATCH],
            matched=prefix_match,
            details=f"'{target_normalized}' starts with '{source_normalized}'" if prefix_match else "",
        ))
        
        # Signal 7: Contains
        contains_match = (source_normalized in target_normalized and
                        len(source_normalized) >= 4 and
                        not normalized_match and
                        not suffix_match and
                        not prefix_match)
        results.append(SignalResult(
            signal=ConfidenceSignal.CONTAINS,
            weight=self.config.signal_weights[ConfidenceSignal.CONTAINS],
            matched=contains_match,
            details=f"'{target_normalized}' contains '{source_normalized}'" if contains_match else "",
        ))
        
        # Signal 8: Single token (weak signal, used when no other match)
        single_token = (overlap_count == 1 and
                       not any(r.matched for r in results))
        results.append(SignalResult(
            signal=ConfidenceSignal.SINGLE_TOKEN,
            weight=self.config.signal_weights[ConfidenceSignal.SINGLE_TOKEN],
            matched=single_token,
            details=f"Single token match: {matched_tokens}" if single_token else "",
            matched_tokens=matched_tokens if single_token else [],
        ))
        
        return results
    
    def _evaluate_penalties(
        self,
        matched_tokens: List[str],
        alternative_match_count: int,
    ) -> List[PenaltyResult]:
        """Evaluate all penalty factors."""
        results = []
        
        # Penalty 1: Short tokens
        short_tokens = [t for t in matched_tokens 
                       if len(t) < self.config.short_token_length]
        if short_tokens:
            results.append(PenaltyResult(
                penalty_type=PenaltyType.SHORT_TOKEN,
                multiplier=self.config.penalty_multipliers[PenaltyType.SHORT_TOKEN],
                reason=f"Short tokens (< {self.config.short_token_length} chars): {short_tokens}",
                affected_tokens=short_tokens,
            ))
        else:
            results.append(PenaltyResult(
                penalty_type=PenaltyType.SHORT_TOKEN,
                multiplier=1.0,
                reason="No short tokens",
            ))
        
        # Penalty 2: Common tokens
        common_found = [t for t in matched_tokens if t in self.config.common_tokens]
        non_common_found = [t for t in matched_tokens if t not in self.config.common_tokens]
        
        # Only apply penalty if ALL matched tokens are common
        if common_found and not non_common_found:
            results.append(PenaltyResult(
                penalty_type=PenaltyType.COMMON_TOKEN,
                multiplier=self.config.penalty_multipliers[PenaltyType.COMMON_TOKEN],
                reason=f"All matched tokens are common: {common_found}",
                affected_tokens=common_found,
            ))
        else:
            results.append(PenaltyResult(
                penalty_type=PenaltyType.COMMON_TOKEN,
                multiplier=1.0,
                reason="Has non-common tokens" if non_common_found else "No common tokens",
            ))
        
        # Penalty 3: Ambiguity (multiple potential matches)
        if alternative_match_count > 2:
            # Stronger penalty for more alternatives
            penalty = self.config.penalty_multipliers[PenaltyType.AMBIGUITY]
            penalty = penalty ** (1 + (alternative_match_count - 2) * 0.2)  # Compound penalty
            results.append(PenaltyResult(
                penalty_type=PenaltyType.AMBIGUITY,
                multiplier=max(0.3, penalty),  # Floor at 0.3
                reason=f"Source has {alternative_match_count} potential matches",
            ))
        else:
            results.append(PenaltyResult(
                penalty_type=PenaltyType.AMBIGUITY,
                multiplier=1.0,
                reason="Low ambiguity" if alternative_match_count <= 1 else "Acceptable ambiguity",
            ))
        
        # Penalty 4: Low-value tokens
        low_value_found = [t for t in matched_tokens if t in self.config.low_value_tokens]
        high_value_found = [t for t in matched_tokens 
                          if t not in self.config.low_value_tokens 
                          and t not in self.config.common_tokens]
        
        # Only apply if majority of tokens are low-value
        if low_value_found and len(low_value_found) > len(high_value_found):
            results.append(PenaltyResult(
                penalty_type=PenaltyType.LOW_VALUE_TOKEN,
                multiplier=self.config.penalty_multipliers[PenaltyType.LOW_VALUE_TOKEN],
                reason=f"Mostly low-value tokens: {low_value_found}",
                affected_tokens=low_value_found,
            ))
        else:
            results.append(PenaltyResult(
                penalty_type=PenaltyType.LOW_VALUE_TOKEN,
                multiplier=1.0,
                reason="Has high-value tokens" if high_value_found else "No low-value tokens",
            ))
        
        return results
    
    def _calculate_base_score(self, signal_results: List[SignalResult]) -> float:
        """
        Calculate base score from signal results.
        
        Uses the maximum weight among matched signals, not sum,
        to avoid inflated scores from multiple weak signals.
        """
        matched_weights = [s.weight for s in signal_results if s.matched]
        if not matched_weights:
            return 0.0
        
        # Use max weight as base, with small bonus for additional signals
        max_weight = max(matched_weights)
        additional_signals = len(matched_weights) - 1
        bonus = min(0.1, additional_signals * 0.02)  # Cap bonus at 0.1
        
        return min(1.0, max_weight + bonus)
    
    def _apply_penalties(
        self,
        base_score: float,
        penalty_results: List[PenaltyResult],
    ) -> float:
        """Apply penalty multipliers to base score."""
        score = base_score
        for penalty in penalty_results:
            score *= penalty.multiplier
        return round(score, 4)
    
    def _build_explanation(
        self,
        source_name: str,
        target_name: str,
        signal_results: List[SignalResult],
        penalty_results: List[PenaltyResult],
        base_score: float,
        final_score: float,
    ) -> str:
        """Build human-readable explanation of the confidence calculation."""
        lines = []
        
        # Header
        lines.append(f"Match: {source_name} → {target_name}")
        lines.append(f"Confidence: {final_score:.2f}")
        lines.append("")
        lines.append("Signals:")
        
        # Matched signals
        matched_signals = [s for s in signal_results if s.matched]
        if matched_signals:
            for signal in matched_signals:
                lines.append(f"  ✓ {signal.signal.value} ({signal.weight:.2f})")
                if signal.details:
                    lines.append(f"    → {signal.details}")
        else:
            lines.append("  (none)")
        
        # Penalties
        applied_penalties = [p for p in penalty_results if p.multiplier < 1.0]
        if applied_penalties:
            lines.append("")
            lines.append("Penalties:")
            for penalty in applied_penalties:
                lines.append(f"  - {penalty.penalty_type.value} (×{penalty.multiplier:.2f})")
                if penalty.reason:
                    lines.append(f"    → {penalty.reason}")
        else:
            lines.append("")
            lines.append("Penalties: None")
        
        return "\n".join(lines)
    
    def explain(self, result: ConfidenceResult) -> str:
        """
        Generate a detailed, formatted explanation of a confidence result.
        
        This is a richer version of the explanation included in the result,
        suitable for CLI output.
        """
        lines = []
        
        lines.append("═" * 60)
        lines.append("MATCH EXPLANATION")
        lines.append("═" * 60)
        lines.append("")
        
        if result.source_node_id:
            lines.append(f"Source: {result.source_node_id}")
        if result.target_node_id:
            lines.append(f"Target: {result.target_node_id}")
        if result.matched_tokens:
            lines.append(f"Matched Tokens: {result.matched_tokens}")
        
        lines.append("")
        lines.append("─" * 60)
        lines.append("CONFIDENCE CALCULATION")
        lines.append("─" * 60)
        lines.append("")
        
        lines.append("Base signals:")
        if result.signals:
            for signal in result.signals:
                weight = signal.get("weight", 0)
                name = signal.get("signal", "unknown")
                details = signal.get("details", "")
                lines.append(f"  [+{weight:.2f}] {name}")
                if details:
                    lines.append(f"         {details}")
        else:
            lines.append("  (none)")
        
        lines.append("")
        lines.append("Penalties:")
        if result.penalties:
            for penalty in result.penalties:
                multiplier = penalty.get("multiplier", 1.0)
                name = penalty.get("penalty_type", "unknown")
                reason = penalty.get("reason", "")
                lines.append(f"  [×{multiplier:.2f}] {name}")
                if reason:
                    lines.append(f"         {reason}")
        else:
            lines.append("  None applied")
        
        lines.append("")
        confidence_level = self._get_confidence_level(result.score)
        lines.append(f"Final confidence: {result.score:.2f} ({confidence_level})")
        lines.append("")
        lines.append("═" * 60)
        
        return "\n".join(lines)
    
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
    def _normalize(name: str) -> str:
        """Normalize a name by lowercasing and removing separators."""
        result = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            result = result.replace(sep, "")
        return result
    
    @staticmethod
    def _signal_to_dict(signal: SignalResult) -> Dict:
        """Convert SignalResult to dictionary."""
        return {
            "signal": signal.signal.value,
            "weight": signal.weight,
            "matched": signal.matched,
            "details": signal.details,
            "matched_tokens": signal.matched_tokens,
        }
    
    @staticmethod
    def _penalty_to_dict(penalty: PenaltyResult) -> Dict:
        """Convert PenaltyResult to dictionary."""
        return {
            "penalty_type": penalty.penalty_type.value,
            "multiplier": penalty.multiplier,
            "reason": penalty.reason,
            "affected_tokens": penalty.affected_tokens,
        }


def create_default_calculator() -> ConfidenceCalculator:
    """Create a ConfidenceCalculator with default configuration."""
    return ConfidenceCalculator()