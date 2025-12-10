"""
Unit tests for the Confidence Calculation Engine.
"""

import pytest
from jnkn.core.confidence import (
    ConfidenceCalculator,
    ConfidenceConfig,
    ConfidenceResult,
    ConfidenceSignal,
    PenaltyType,
    SignalResult,
    PenaltyResult,
    create_default_calculator,
)

class TestConfidenceCalculator:
    
    @pytest.fixture
    def calculator(self):
        return create_default_calculator()

    def test_initialization(self):
        """Test default initialization and custom config."""
        calc = create_default_calculator()
        assert isinstance(calc.config, ConfidenceConfig)
        
        custom_config = ConfidenceConfig(min_token_overlap_high=5)
        calc_custom = ConfidenceCalculator(config=custom_config)
        assert calc_custom.config.min_token_overlap_high == 5

    def test_normalize(self):
        """Test name normalization logic."""
        # Test separators and casing
        assert ConfidenceCalculator._normalize("PAYMENT_DB_HOST") == "paymentdbhost"
        assert ConfidenceCalculator._normalize("api.v1-endpoint") == "apiv1endpoint"
        assert ConfidenceCalculator._normalize("mixed/SEPARATOR:test") == "mixedseparatortest"

    def test_evaluate_signals_exact_match(self, calculator):
        """Test EXACT_MATCH signal."""
        results = calculator._evaluate_signals(
            "DB_HOST", "DB_HOST", ["db", "host"], ["db", "host"], ["db", "host"]
        )
        exact = next(r for r in results if r.signal == ConfidenceSignal.EXACT_MATCH)
        assert exact.matched is True
        assert exact.weight == 1.0

    def test_evaluate_signals_normalized_match(self, calculator):
        """Test NORMALIZED_MATCH signal."""
        results = calculator._evaluate_signals(
            "DB_HOST", "db-host", ["db", "host"], ["db", "host"], ["db", "host"]
        )
        norm = next(r for r in results if r.signal == ConfidenceSignal.NORMALIZED_MATCH)
        assert norm.matched is True
        # Ensure exact match is False to prevent double counting logic
        exact = next(r for r in results if r.signal == ConfidenceSignal.EXACT_MATCH)
        assert exact.matched is False

    def test_evaluate_signals_overlap(self, calculator):
        """Test token overlap signals."""
        # High overlap (3 tokens default)
        tokens = ["a", "b", "c", "d"] # Assuming 'a' is not common/short for this test context or using config
        # Use simpler tokens that pass filters: length >= 4
        t_list = ["alpha", "beta", "gamma"] 
        results = calculator._evaluate_signals(
            "src", "tgt", t_list, t_list, t_list
        )
        high = next(r for r in results if r.signal == ConfidenceSignal.TOKEN_OVERLAP_HIGH)
        assert high.matched is True

        # Medium overlap (2 tokens)
        t_med = ["alpha", "beta"]
        results = calculator._evaluate_signals(
            "src", "tgt", t_med, t_med, t_med
        )
        high = next(r for r in results if r.signal == ConfidenceSignal.TOKEN_OVERLAP_HIGH)
        med = next(r for r in results if r.signal == ConfidenceSignal.TOKEN_OVERLAP_MEDIUM)
        assert high.matched is False
        assert med.matched is True

    def test_evaluate_signals_structural(self, calculator):
        """Test Suffix, Prefix, and Contains."""
        # Suffix
        results = calculator._evaluate_signals(
            "host", "db_host", ["host"], ["db", "host"], ["host"]
        )
        suffix = next(r for r in results if r.signal == ConfidenceSignal.SUFFIX_MATCH)
        assert suffix.matched is True

        # Prefix
        results = calculator._evaluate_signals(
            "user", "user_id", ["user"], ["user", "id"], ["user"]
        )
        prefix = next(r for r in results if r.signal == ConfidenceSignal.PREFIX_MATCH)
        assert prefix.matched is True

        # Contains
        # Use a true substring that is not a prefix or suffix
        # "base" inside "database_url"
        results = calculator._evaluate_signals(
            "base", "database_url", ["base"], ["database", "url"], [] 
        )
        contains = next(r for r in results if r.signal == ConfidenceSignal.CONTAINS)
        assert contains.matched is True

    def test_evaluate_signals_single_token(self, calculator):
        """Test single token match fallback."""
        # Setup scenario where no other signal matches
        results = calculator._evaluate_signals(
            "foo", "bar", ["foo"], ["bar"], ["common"]
        )
        single = next(r for r in results if r.signal == ConfidenceSignal.SINGLE_TOKEN)
        assert single.matched is True

    def test_evaluate_penalties(self, calculator):
        """Test all penalty types."""
        # 1. Short Tokens
        res = calculator._evaluate_penalties(["a", "b"], 0)
        short = next(r for r in res if r.penalty_type == PenaltyType.SHORT_TOKEN)
        assert short.multiplier < 1.0

        # No short tokens
        res = calculator._evaluate_penalties(["longtoken"], 0)
        short = next(r for r in res if r.penalty_type == PenaltyType.SHORT_TOKEN)
        assert short.multiplier == 1.0

        # 2. Common Tokens
        # Need to ensure token is in config.common_tokens
        res = calculator._evaluate_penalties(["id"], 0) 
        common = next(r for r in res if r.penalty_type == PenaltyType.COMMON_TOKEN)
        assert common.multiplier < 1.0

        # Mixed common/uncommon
        res = calculator._evaluate_penalties(["id", "uniquevalue"], 0)
        common = next(r for r in res if r.penalty_type == PenaltyType.COMMON_TOKEN)
        assert common.multiplier == 1.0

        # 3. Ambiguity
        # High ambiguity
        res = calculator._evaluate_penalties([], 5)
        ambig = next(r for r in res if r.penalty_type == PenaltyType.AMBIGUITY)
        assert ambig.multiplier < 1.0
        
        # Low ambiguity
        res = calculator._evaluate_penalties([], 1)
        ambig = next(r for r in res if r.penalty_type == PenaltyType.AMBIGUITY)
        assert ambig.multiplier == 1.0

        # 4. Low Value Tokens
        # "prod" is usually in low_value_tokens defaults
        res = calculator._evaluate_penalties(["prod", "aws"], 0)
        low_val = next(r for r in res if r.penalty_type == PenaltyType.LOW_VALUE_TOKEN)
        assert low_val.multiplier < 1.0

        # High value exists
        res = calculator._evaluate_penalties(["prod", "specific_service_name"], 0)
        low_val = next(r for r in res if r.penalty_type == PenaltyType.LOW_VALUE_TOKEN)
        assert low_val.multiplier == 1.0

    def test_calculate_base_score(self, calculator):
        """Test score aggregation logic."""
        # No matches
        assert calculator._calculate_base_score([]) == 0.0

        # Max weight selection + bonus
        s1 = SignalResult(ConfidenceSignal.EXACT_MATCH, 0.8, True)
        s2 = SignalResult(ConfidenceSignal.SUFFIX_MATCH, 0.5, True)
        
        score = calculator._calculate_base_score([s1, s2])
        # Base 0.8 + Bonus (1 extra signal * 0.02) = 0.82
        assert score == pytest.approx(0.82)

        # Test capping at 1.0
        s3 = SignalResult(ConfidenceSignal.EXACT_MATCH, 1.0, True)
        # Add many signals to try to exceed 1.0
        signals = [s3] + [s2] * 10
        assert calculator._calculate_base_score(signals) == 1.0

    def test_full_calculate_flow(self, calculator):
        """Test the public calculate method end-to-end."""
        # Use names with tokens > 3 chars to avoid short_token penalty
        # which heavily reduces score (x0.5)
        result = calculator.calculate(
            source_name="PAYMENT_DATABASE",
            target_name="payment_database",
            source_tokens=["payment", "database"],
            target_tokens=["payment", "database"],
            alternative_match_count=0
        )
        assert isinstance(result, ConfidenceResult)
        # 0.9 base (normalized) * 1.0 (no penalties) = 0.9
        assert result.score > 0.8
        # Check that matched_tokens were computed automatically
        assert "payment" in result.matched_tokens
        assert result.explanation != ""

    def test_explanation_building(self, calculator):
        """Test text generation for explanations."""
        result = calculator.calculate(
            "A", "B", ["a"], ["b"], matched_tokens=[]
        )
        assert "Penalties: None" in result.explanation
        assert "(none)" in result.explanation # No signals

        # Test with signals and penalties
        result = calculator.calculate(
            "id", "id", ["id"], ["id"] # Matches but is short/common
        )
        assert "exact_match" in result.explanation.lower()
        assert "short_token" in result.explanation.lower()

    def test_explain_formatting_method(self, calculator):
        """Test the explain() method formatting."""
        res_obj = ConfidenceResult(
            score=0.9,
            signals=[{
                "signal": "test_sig", 
                "weight": 0.5, 
                "matched": True, 
                "details": "det"
            }],
            penalties=[{
                "penalty_type": "test_pen", 
                "multiplier": 0.5, 
                "reason": "reas"
            }],
            source_node_id="src",
            target_node_id="tgt"
        )
        
        text = calculator.explain(res_obj)
        assert "MATCH EXPLANATION" in text
        assert "Source: src" in text
        assert "test_sig" in text
        assert "test_pen" in text
        assert "HIGH" in text # 0.9 score

        # Test branch where matched_tokens is present
        res_obj.matched_tokens = ["a"]
        text = calculator.explain(res_obj)
        assert "Matched Tokens: ['a']" in text

        # Test branch where signal has matched_tokens
        # Construct fresh object to avoid ambiguity in test state
        res_obj_2 = ConfidenceResult(
            score=0.5,
            signals=[{
                "signal": "sig",
                "weight": 0.5,
                "matched": True,
                "matched_tokens": ["x"]
            }]
        )
        text = calculator.explain(res_obj_2)
        assert "['x']" in text

    def test_confidence_levels(self, calculator):
        assert calculator._get_confidence_level(0.9) == "HIGH"
        assert calculator._get_confidence_level(0.7) == "MEDIUM"
        assert calculator._get_confidence_level(0.5) == "LOW"
        assert calculator._get_confidence_level(0.2) == "VERY LOW"

    def test_dictionaries_helpers(self, calculator):
        """Test helper methods that convert dataclasses to dicts."""
        sig = SignalResult(ConfidenceSignal.EXACT_MATCH, 1.0, True)
        d = calculator._signal_to_dict(sig)
        assert d['signal'] == 'exact_match'

        pen = PenaltyResult(PenaltyType.SHORT_TOKEN, 0.5)
        d = calculator._penalty_to_dict(pen)
        assert d['penalty_type'] == 'short_token'