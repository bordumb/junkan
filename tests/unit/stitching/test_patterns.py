"""
Unit tests for suppression pattern generation logic.
"""

import pytest
from jnkn.stitching.patterns import suggest_patterns


class TestSuggestPatterns:
    
    def test_exact_match_only_for_simple_ids(self):
        """Test simple IDs without separators get limited suggestions."""
        patterns = suggest_patterns("simple_id")
        assert patterns == ["simple_id"]

    def test_env_var_patterns(self):
        """Test typical environment variable patterns."""
        # Scenario: Payment API Key
        patterns = suggest_patterns("env:PAYMENT_API_KEY")
        
        assert "env:PAYMENT_API_KEY" in patterns  # Exact
        assert "env:PAYMENT_*" in patterns        # Prefix (grouped vars)
        assert "env:*_KEY" in patterns            # Suffix (semantic type)
        assert "env:*" in patterns                # Wildcard fallback

    def test_infra_resource_patterns(self):
        """Test Terraform resource patterns."""
        # Scenario: AWS RDS Instance
        patterns = suggest_patterns("infra:aws_db_instance.payment")
        
        assert "infra:aws_db_instance.payment" in patterns
        assert "infra:aws_db_instance.*" in patterns # Resource type wildcard
        assert "infra:*" in patterns

    def test_specific_suffixes(self):
        """Test specific high-noise suffix handling."""
        # _ID
        assert "env:*_ID" in suggest_patterns("env:USER_ID")
        # _HOST
        assert "env:*_HOST" in suggest_patterns("env:DB_HOST")
        # _URL
        assert "env:*_URL" in suggest_patterns("env:SERVICE_URL")

    def test_no_colon_handling(self):
        """Ensure it handles IDs without colons gracefully."""
        assert suggest_patterns("just_a_string") == ["just_a_string"]