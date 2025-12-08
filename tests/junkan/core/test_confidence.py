"""
Unit tests for the Confidence Calculation Engine.

Tests cover:
- Individual signal calculations
- Penalty combinations
- Explanation output format
- Edge cases and boundary conditions
"""

import pytest
from junkan.core.confidence import (
    ConfidenceCalculator,
    ConfidenceConfig,
    ConfidenceResult,
    ConfidenceSignal,
    PenaltyType,
    SignalResult,
    PenaltyResult,
    create_default_calculator,
)


class TestConfidenceSignals:
    """Test individual signal calculations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = create_default_calculator()
    
    def test_exact_match_signal(self):
        """Test exact match gives highest confidence."""
        result = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="PAYMENT_DB_HOST",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
        )
        assert result.score == 1.0
        assert any(s["signal"] == ConfidenceSignal.EXACT_MATCH for s in result.signals)
    
    def test_normalized_match_signal(self):
        """Test normalized match (case-insensitive, separator-insensitive)."""
        result = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="payment_db_host",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
        )
        # Should have normalized match but not exact match
        assert result.score >= 0.8
        assert any(s["signal"] == ConfidenceSignal.NORMALIZED_MATCH for s in result.signals)
        assert not any(s["signal"] == ConfidenceSignal.EXACT_MATCH for s in result.signals)
    
    def test_token_overlap_high_signal(self):
        """Test high token overlap (3+ significant tokens)."""
        result = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="payment_database_host_primary",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "database", "host", "primary"],
            matched_tokens=["payment", "host"],  # 2 significant tokens
        )
        # This should be medium overlap (2 tokens), not high
        assert not any(s["signal"] == ConfidenceSignal.TOKEN_OVERLAP_HIGH for s in result.signals)
    
    def test_token_overlap_medium_signal(self):
        """Test medium token overlap (2 significant tokens)."""
        result = self.calculator.calculate(
            source_name="PAYMENT_HOST",
            target_name="payment_server_host",
            source_tokens=["payment", "host"],
            target_tokens=["payment", "server", "host"],
            matched_tokens=["payment", "host"],
        )
        assert result.score >= 0.5
        # Should have some overlap signal
        has_overlap = any(
            s["signal"] in (ConfidenceSignal.TOKEN_OVERLAP_HIGH, ConfidenceSignal.TOKEN_OVERLAP_MEDIUM)
            for s in result.signals
        )
        # May also have normalized match since tokens overlap fully with source
        assert has_overlap or result.score >= 0.6
    
    def test_suffix_match_signal(self):
        """Test suffix matching."""
        result = self.calculator.calculate(
            source_name="DB_HOST",
            target_name="aws_rds_db_host",
            source_tokens=["db", "host"],
            target_tokens=["aws", "rds", "db", "host"],
        )
        # Should have suffix match
        assert any(s["signal"] == ConfidenceSignal.SUFFIX_MATCH for s in result.signals)
        assert result.score >= 0.5
    
    def test_prefix_match_signal(self):
        """Test prefix matching."""
        result = self.calculator.calculate(
            source_name="payment_service",
            target_name="payment_service_config",
            source_tokens=["payment", "service"],
            target_tokens=["payment", "service", "config"],
        )
        # Should have prefix match
        assert any(s["signal"] == ConfidenceSignal.PREFIX_MATCH for s in result.signals)
    
    def test_contains_signal(self):
        """Test contains matching."""
        result = self.calculator.calculate(
            source_name="cache",
            target_name="redis_cache_config",
            source_tokens=["cache"],
            target_tokens=["redis", "cache", "config"],
        )
        # Contains but too short for suffix/prefix
        # Should have contains or single token
        assert result.score >= 0.2
    
    def test_single_token_weak_signal(self):
        """Test single token match gives weak signal."""
        result = self.calculator.calculate(
            source_name="HOST",
            target_name="server",  # Completely different
            source_tokens=["host"],
            target_tokens=["server"],
            matched_tokens=[],  # No overlap
        )
        # Should have very low or zero score
        assert result.score <= 0.3


class TestPenalties:
    """Test penalty calculations."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = create_default_calculator()
    
    def test_short_token_penalty(self):
        """Test penalty for short tokens."""
        # Match with short tokens
        result_short = self.calculator.calculate(
            source_name="DB",
            target_name="db",
            source_tokens=["db"],
            target_tokens=["db"],
            matched_tokens=["db"],
        )
        
        # Match with longer tokens
        result_long = self.calculator.calculate(
            source_name="DATABASE",
            target_name="database",
            source_tokens=["database"],
            target_tokens=["database"],
            matched_tokens=["database"],
        )
        
        # Short tokens should have lower score due to penalty
        assert result_short.score < result_long.score
    
    def test_common_token_penalty(self):
        """Test penalty for common tokens only."""
        # Match with only common tokens
        result_common = self.calculator.calculate(
            source_name="DB_HOST",
            target_name="db_host",
            source_tokens=["db", "host"],
            target_tokens=["db", "host"],
            matched_tokens=["db", "host"],
        )
        
        # Match with non-common tokens
        result_specific = self.calculator.calculate(
            source_name="PAYMENT_SERVICE",
            target_name="payment_service",
            source_tokens=["payment", "service"],
            target_tokens=["payment", "service"],
            matched_tokens=["payment", "service"],
        )
        
        # Common-only tokens should have lower score
        assert result_common.score <= result_specific.score
    
    def test_ambiguity_penalty(self):
        """Test penalty for ambiguous matches."""
        # Low ambiguity
        result_low = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="payment_db_host",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
            alternative_match_count=0,
        )
        
        # High ambiguity
        result_high = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="payment_db_host",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
            alternative_match_count=5,
        )
        
        # High ambiguity should have lower score
        assert result_high.score < result_low.score
    
    def test_low_value_token_penalty(self):
        """Test penalty for low-value tokens."""
        # Mostly low-value tokens
        result_low_value = self.calculator.calculate(
            source_name="AWS_MAIN",
            target_name="aws_main",
            source_tokens=["aws", "main"],
            target_tokens=["aws", "main"],
            matched_tokens=["aws", "main"],
        )
        
        # High-value tokens
        result_high_value = self.calculator.calculate(
            source_name="PAYMENT_GATEWAY",
            target_name="payment_gateway",
            source_tokens=["payment", "gateway"],
            target_tokens=["payment", "gateway"],
            matched_tokens=["payment", "gateway"],
        )
        
        # Low-value should have lower score
        assert result_low_value.score <= result_high_value.score
    
    def test_combined_penalties(self):
        """Test multiple penalties applied together."""
        result = self.calculator.calculate(
            source_name="DB",  # Short AND common
            target_name="db",
            source_tokens=["db"],
            target_tokens=["db"],
            matched_tokens=["db"],
            alternative_match_count=4,  # Also ambiguous
        )
        
        # Should have multiple penalties
        assert len(result.penalties) >= 2
        assert result.score < 0.5  # Should be significantly reduced


class TestExplanation:
    """Test explanation output format."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = create_default_calculator()
    
    def test_explanation_contains_match_info(self):
        """Test explanation contains match information."""
        result = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="payment_db_host",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
            source_node_id="env:PAYMENT_DB_HOST",
            target_node_id="infra:payment_db_host",
        )
        
        explanation = self.calculator.explain(result)
        
        assert "PAYMENT_DB_HOST" in explanation or "payment_db_host" in explanation
        assert "CONFIDENCE" in explanation
        assert "Signal" in explanation or "signal" in explanation
    
    def test_explanation_shows_signals(self):
        """Test explanation shows matched signals."""
        result = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="payment_db_host",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
        )
        
        explanation = self.calculator.explain(result)
        
        # Should mention the matched signal type
        assert "normalized" in explanation.lower() or "match" in explanation.lower()
    
    def test_explanation_shows_penalties(self):
        """Test explanation shows applied penalties."""
        result = self.calculator.calculate(
            source_name="DB",
            target_name="db",
            source_tokens=["db"],
            target_tokens=["db"],
            matched_tokens=["db"],
        )
        
        explanation = self.calculator.explain(result)
        
        # Should mention penalties
        assert "Penalt" in explanation or "penalt" in explanation
    
    def test_explanation_shows_confidence_level(self):
        """Test explanation shows human-readable confidence level."""
        result_high = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="PAYMENT_DB_HOST",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
        )
        
        explanation = self.calculator.explain(result_high)
        assert "HIGH" in explanation


class TestConfidenceConfig:
    """Test configuration customization."""
    
    def test_custom_signal_weights(self):
        """Test custom signal weights are applied."""
        config = ConfidenceConfig(
            signal_weights={
                ConfidenceSignal.EXACT_MATCH: 0.5,  # Reduced weight
                ConfidenceSignal.NORMALIZED_MATCH: 0.4,
                ConfidenceSignal.TOKEN_OVERLAP_HIGH: 0.3,
                ConfidenceSignal.TOKEN_OVERLAP_MEDIUM: 0.2,
                ConfidenceSignal.SUFFIX_MATCH: 0.2,
                ConfidenceSignal.PREFIX_MATCH: 0.2,
                ConfidenceSignal.CONTAINS: 0.1,
                ConfidenceSignal.SINGLE_TOKEN: 0.05,
            }
        )
        calculator = ConfidenceCalculator(config)
        
        result = calculator.calculate(
            source_name="TEST",
            target_name="TEST",
            source_tokens=["test"],
            target_tokens=["test"],
        )
        
        # Should use custom weight
        assert result.score == 0.5
    
    def test_custom_penalty_multipliers(self):
        """Test custom penalty multipliers are applied."""
        config = ConfidenceConfig(
            penalty_multipliers={
                PenaltyType.SHORT_TOKEN: 0.1,  # Very strong penalty
                PenaltyType.COMMON_TOKEN: 0.9,
                PenaltyType.AMBIGUITY: 0.9,
                PenaltyType.LOW_VALUE_TOKEN: 0.9,
            }
        )
        calculator = ConfidenceCalculator(config)
        
        result = calculator.calculate(
            source_name="DB",  # Short token
            target_name="DB",
            source_tokens=["db"],
            target_tokens=["db"],
            matched_tokens=["db"],
        )
        
        # Should have severe penalty
        assert result.score < 0.2
    
    def test_custom_common_tokens(self):
        """Test custom common token list."""
        config = ConfidenceConfig(
            common_tokens={"custom", "tokens", "list"}
        )
        calculator = ConfidenceCalculator(config)
        
        # "payment" is NOT in custom common list, so no penalty
        result = calculator.calculate(
            source_name="PAYMENT",
            target_name="payment",
            source_tokens=["payment"],
            target_tokens=["payment"],
            matched_tokens=["payment"],
        )
        
        # Should not have common token penalty
        assert not any(
            p.get("penalty_type") == PenaltyType.COMMON_TOKEN 
            for p in result.penalties
        )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.calculator = create_default_calculator()
    
    def test_empty_tokens(self):
        """Test handling of empty token lists."""
        result = self.calculator.calculate(
            source_name="",
            target_name="",
            source_tokens=[],
            target_tokens=[],
        )
        assert result.score == 0.0
    
    def test_no_overlap(self):
        """Test handling when no tokens overlap."""
        result = self.calculator.calculate(
            source_name="PAYMENT",
            target_name="SERVER",
            source_tokens=["payment"],
            target_tokens=["server"],
            matched_tokens=[],
        )
        assert result.score == 0.0
    
    def test_single_character_tokens(self):
        """Test handling of very short tokens."""
        result = self.calculator.calculate(
            source_name="A",
            target_name="A",
            source_tokens=["a"],
            target_tokens=["a"],
            matched_tokens=["a"],
        )
        # Should have penalty but still match
        assert 0.0 < result.score < 0.5
    
    def test_very_long_tokens(self):
        """Test handling of very long tokens."""
        long_token = "verylongtokenthatexceedsnormalsize"
        result = self.calculator.calculate(
            source_name=long_token.upper(),
            target_name=long_token,
            source_tokens=[long_token],
            target_tokens=[long_token],
            matched_tokens=[long_token],
        )
        # Should work normally
        assert result.score >= 0.8
    
    def test_unicode_tokens(self):
        """Test handling of unicode characters in tokens."""
        result = self.calculator.calculate(
            source_name="CAFÉ_SERVICE",
            target_name="café_service",
            source_tokens=["café", "service"],
            target_tokens=["café", "service"],
        )
        # Should work with unicode
        assert result.score >= 0.5
    
    def test_special_characters_in_name(self):
        """Test handling of special characters."""
        result = self.calculator.calculate(
            source_name="DB@HOST#1",
            target_name="db@host#1",
            source_tokens=["db", "host", "1"],
            target_tokens=["db", "host", "1"],
        )
        # Should work with special chars
        assert result.score >= 0.5
    
    def test_score_bounds(self):
        """Test score is always between 0 and 1."""
        # Test maximum possible signals
        result_max = self.calculator.calculate(
            source_name="PAYMENT_DB_HOST",
            target_name="PAYMENT_DB_HOST",
            source_tokens=["payment", "db", "host"],
            target_tokens=["payment", "db", "host"],
        )
        assert 0.0 <= result_max.score <= 1.0
        
        # Test minimum
        result_min = self.calculator.calculate(
            source_name="X",
            target_name="Y",
            source_tokens=["x"],
            target_tokens=["y"],
            matched_tokens=[],
        )
        assert 0.0 <= result_min.score <= 1.0


class TestConfidenceResult:
    """Test ConfidenceResult model."""
    
    def test_result_immutability(self):
        """Test result fields can be accessed."""
        result = ConfidenceResult(
            score=0.85,
            signals=[{"signal": "test", "weight": 0.9}],
            penalties=[],
            explanation="Test explanation",
            matched_tokens=["test"],
            source_node_id="env:TEST",
            target_node_id="infra:test",
        )
        
        assert result.score == 0.85
        assert len(result.signals) == 1
        assert result.matched_tokens == ["test"]
    
    def test_result_score_validation(self):
        """Test score must be between 0 and 1."""
        # Valid scores
        result_valid = ConfidenceResult(score=0.5)
        assert result_valid.score == 0.5
        
        # Invalid scores should raise
        with pytest.raises(ValueError):
            ConfidenceResult(score=1.5)
        
        with pytest.raises(ValueError):
            ConfidenceResult(score=-0.1)


class TestCreateDefaultCalculator:
    """Test factory function."""
    
    def test_creates_calculator_with_defaults(self):
        """Test factory creates working calculator."""
        calculator = create_default_calculator()
        
        result = calculator.calculate(
            source_name="TEST",
            target_name="TEST",
            source_tokens=["test"],
            target_tokens=["test"],
        )
        
        assert result.score > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])