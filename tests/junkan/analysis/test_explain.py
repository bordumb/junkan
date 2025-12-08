"""
Unit tests for the Match Explanation Generator.

Tests cover:
- Explanation generation
- CLI output formatting
- Alternative match finding
- Edge cases
"""

import pytest
from typing import List

from junkan.analysis.explain import (
    ExplanationGenerator,
    MatchExplanation,
    NodeInfo,
    AlternativeMatch,
    create_explanation_generator,
)
from junkan.core.confidence import ConfidenceResult
from junkan.core.graph import DependencyGraph
from junkan.core.types import Node, Edge, NodeType, RelationshipType


class TestNodeInfo:
    """Test NodeInfo dataclass."""
    
    def test_basic_creation(self):
        """Test creating NodeInfo."""
        info = NodeInfo(
            id="env:DATABASE_URL",
            name="DATABASE_URL",
            type="env_var",
            tokens=["database", "url"],
        )
        
        assert info.id == "env:DATABASE_URL"
        assert info.name == "DATABASE_URL"
        assert info.tokens == ["database", "url"]
    
    def test_with_optional_fields(self):
        """Test NodeInfo with optional fields."""
        info = NodeInfo(
            id="env:DATABASE_URL",
            name="DATABASE_URL",
            type="env_var",
            tokens=["database", "url"],
            path="src/config.py",
            line_number=42,
            metadata={"source": "os.getenv"},
        )
        
        assert info.path == "src/config.py"
        assert info.line_number == 42
        assert info.metadata["source"] == "os.getenv"


class TestAlternativeMatch:
    """Test AlternativeMatch dataclass."""
    
    def test_basic_creation(self):
        """Test creating AlternativeMatch."""
        alt = AlternativeMatch(
            node_id="infra:other_db",
            node_name="other_db",
            score=0.45,
            rejection_reason="rejected: below threshold (0.5)",
        )
        
        assert alt.node_id == "infra:other_db"
        assert alt.score == 0.45


class TestExplanationGenerator:
    """Test ExplanationGenerator."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.graph = DependencyGraph()
        
        # Add some nodes
        self.graph.add_node(Node(
            id="env:PAYMENT_DB_HOST",
            name="PAYMENT_DB_HOST",
            type=NodeType.ENV_VAR,
            path="src/app.py",
            metadata={"line": 42},
        ))
        
        self.graph.add_node(Node(
            id="infra:payment_db_host",
            name="payment_db_host",
            type=NodeType.INFRA_RESOURCE,
            path="terraform/rds.tf",
            metadata={"line": 15},
        ))
        
        self.graph.add_node(Node(
            id="infra:db_host_backup",
            name="db_host_backup",
            type=NodeType.INFRA_RESOURCE,
            path="terraform/rds.tf",
        ))
        
        self.graph.add_node(Node(
            id="infra:payment_service",
            name="payment_service",
            type=NodeType.INFRA_RESOURCE,
            path="terraform/ecs.tf",
        ))
        
        # Add an edge
        self.graph.add_edge(Edge(
            source_id="env:PAYMENT_DB_HOST",
            target_id="infra:payment_db_host",
            type=RelationshipType.PROVIDES,
            confidence=0.92,
            metadata={
                "rule": "EnvVarToInfraRule",
                "matched_tokens": ["payment", "db", "host"],
            },
        ))
        
        self.generator = ExplanationGenerator(
            graph=self.graph,
            min_confidence=0.5,
        )
    
    def test_explain_existing_match(self):
        """Test explaining an existing match."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        assert explanation.source.id == "env:PAYMENT_DB_HOST"
        assert explanation.target.id == "infra:payment_db_host"
        assert explanation.edge_exists is True
        assert explanation.confidence_result.score > 0.5
    
    def test_explain_hypothetical_match(self):
        """Test explaining a match that doesn't exist."""
        # Remove the edge first
        self.graph._graph.remove_edge(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host"
        )
        
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        assert explanation.edge_exists is False
        assert explanation.confidence_result.score > 0.5
    
    def test_explain_finds_source_info(self):
        """Test that source node info is populated."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        assert explanation.source.name == "PAYMENT_DB_HOST"
        assert explanation.source.type == "env_var"
        assert "payment" in explanation.source.tokens
        assert explanation.source.path == "src/app.py"
    
    def test_explain_finds_target_info(self):
        """Test that target node info is populated."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        assert explanation.target.name == "payment_db_host"
        assert explanation.target.type == "infra_resource"
        assert "payment" in explanation.target.tokens
    
    def test_explain_finds_alternatives(self):
        """Test that alternative matches are found."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
            find_alternatives=True,
        )
        
        # Should find db_host_backup and payment_service as alternatives
        assert len(explanation.alternatives) > 0
        
        alt_ids = [a.node_id for a in explanation.alternatives]
        # At least one of these should be in alternatives
        assert any(
            alt_id in ["infra:db_host_backup", "infra:payment_service"]
            for alt_id in alt_ids
        )
    
    def test_explain_without_alternatives(self):
        """Test explanation without finding alternatives."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
            find_alternatives=False,
        )
        
        assert explanation.alternatives == []
    
    def test_explain_unknown_nodes(self):
        """Test explaining nodes not in graph."""
        explanation = self.generator.explain(
            "env:UNKNOWN_VAR",
            "infra:unknown_resource",
        )
        
        # Should still work by inferring from IDs
        assert explanation.source.id == "env:UNKNOWN_VAR"
        assert explanation.source.name == "UNKNOWN_VAR"
        assert explanation.source.type == "env_var"


class TestExplanationFormatting:
    """Test explanation formatting."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ExplanationGenerator(min_confidence=0.5)
    
    def test_format_contains_headers(self):
        """Test formatted output contains headers."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        formatted = self.generator.format(explanation)
        
        assert "MATCH EXPLANATION" in formatted
        assert "CONFIDENCE CALCULATION" in formatted
    
    def test_format_contains_source_info(self):
        """Test formatted output contains source info."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        formatted = self.generator.format(explanation)
        
        assert "Source:" in formatted
        assert "PAYMENT_DB_HOST" in formatted
    
    def test_format_contains_target_info(self):
        """Test formatted output contains target info."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        formatted = self.generator.format(explanation)
        
        assert "Target:" in formatted
        assert "payment_db_host" in formatted
    
    def test_format_contains_confidence_score(self):
        """Test formatted output contains confidence score."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        formatted = self.generator.format(explanation)
        
        assert "Final confidence:" in formatted
        # Should contain a confidence level
        assert any(level in formatted for level in ["HIGH", "MEDIUM", "LOW"])
    
    def test_format_brief(self):
        """Test brief format."""
        explanation = self.generator.explain(
            "env:PAYMENT_DB_HOST",
            "infra:payment_db_host",
        )
        
        brief = self.generator.format_brief(explanation)
        
        assert "PAYMENT_DB_HOST" in brief
        assert "payment_db_host" in brief
        assert "->" in brief


class TestExplainWhyNot:
    """Test explain_why_not method."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ExplanationGenerator(min_confidence=0.5)
    
    def test_explain_why_not_low_score(self):
        """Test explaining why match has low score."""
        result = self.generator.explain_why_not(
            "env:HOST",  # Very generic
            "infra:completely_different_name",
        )
        
        assert "below threshold" in result.lower() or "no overlapping" in result.lower()
    
    def test_explain_why_not_shows_tokens(self):
        """Test that tokens are shown in explanation."""
        result = self.generator.explain_why_not(
            "env:DATABASE_URL",
            "infra:redis_cache",
        )
        
        assert "tokens" in result.lower() or "token" in result.lower()


class TestTypeInference:
    """Test type inference from node IDs."""
    
    def test_infer_env_var_type(self):
        """Test inferring env_var type."""
        result = ExplanationGenerator._infer_type_from_id("env:DATABASE_URL")
        assert result == "env_var"
    
    def test_infer_infra_type(self):
        """Test inferring infra_resource type."""
        result = ExplanationGenerator._infer_type_from_id("infra:rds_main")
        assert result == "infra_resource"
    
    def test_infer_file_type(self):
        """Test inferring code_file type."""
        result = ExplanationGenerator._infer_type_from_id("file://src/app.py")
        assert result == "code_file"
    
    def test_infer_unknown_type(self):
        """Test unknown type for unrecognized prefix."""
        result = ExplanationGenerator._infer_type_from_id("something:else")
        assert result == "unknown"


class TestTokenization:
    """Test tokenization helper."""
    
    def test_tokenize_underscore(self):
        """Test tokenizing underscore-separated names."""
        result = ExplanationGenerator._tokenize("PAYMENT_DB_HOST")
        assert result == ["payment", "db", "host"]
    
    def test_tokenize_dots(self):
        """Test tokenizing dot-separated names."""
        result = ExplanationGenerator._tokenize("aws.rds.main")
        assert result == ["aws", "rds", "main"]
    
    def test_tokenize_mixed(self):
        """Test tokenizing mixed separators."""
        result = ExplanationGenerator._tokenize("aws_rds.main-db")
        assert result == ["aws", "rds", "main", "db"]


class TestNameExtraction:
    """Test name extraction from IDs."""
    
    def test_extract_from_colon_id(self):
        """Test extracting name from colon-prefixed ID."""
        result = ExplanationGenerator._extract_name_from_id("env:DATABASE_URL")
        assert result == "DATABASE_URL"
    
    def test_extract_from_url_id(self):
        """Test extracting name from URL-style ID."""
        result = ExplanationGenerator._extract_name_from_id("file://src/app.py")
        assert result == "src/app.py"
    
    def test_extract_from_plain_id(self):
        """Test extracting name from plain ID."""
        result = ExplanationGenerator._extract_name_from_id("plain_name")
        assert result == "plain_name"


class TestFactoryFunction:
    """Test factory function."""
    
    def test_creates_generator(self):
        """Test factory creates working generator."""
        generator = create_explanation_generator()
        
        explanation = generator.explain(
            "env:DATABASE_URL",
            "infra:database",
        )
        
        assert explanation is not None
        assert explanation.confidence_result is not None
    
    def test_creates_with_custom_threshold(self):
        """Test factory with custom threshold."""
        generator = create_explanation_generator(min_confidence=0.8)
        
        assert generator.min_confidence == 0.8


class TestEdgeCases:
    """Test edge cases."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.generator = ExplanationGenerator(min_confidence=0.5)
    
    def test_empty_node_ids(self):
        """Test handling empty node IDs."""
        explanation = self.generator.explain("", "")
        
        assert explanation is not None
        assert explanation.confidence_result.score == 0.0
    
    def test_unicode_in_names(self):
        """Test handling unicode characters."""
        explanation = self.generator.explain(
            "env:CAFÉ_URL",
            "infra:café_service",
        )
        
        assert explanation is not None
        assert "café" in explanation.source.tokens or "caf" in explanation.source.tokens[0]
    
    def test_very_long_names(self):
        """Test handling very long names."""
        long_name = "very_" * 50 + "long_name"
        explanation = self.generator.explain(
            f"env:{long_name}",
            f"infra:{long_name}",
        )
        
        assert explanation is not None
        assert explanation.confidence_result.score > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])