"""
Tests for Top Findings extraction.
"""

import pytest
from unittest.mock import MagicMock, patch

from jnkn.analysis.top_findings import (
    Finding,
    FindingType,
    TopFindingsSummary,
    TopFindingsExtractor,
)
from jnkn.core.types import Node, Edge, NodeType, RelationshipType


class TestFinding:
    """Tests for Finding dataclass."""
    
    def test_to_dict(self):
        """Test converting finding to dictionary."""
        source = Node(
            id="env:TEST",
            name="TEST",
            type=NodeType.ENV_VAR,
            path="test.py"
        )
        
        finding = Finding(
            type=FindingType.HIGH_CONFIDENCE_LINK,
            title="TEST → output",
            description="Test description",
            confidence=0.85,
            interest_score=3.0,
            source_node=source,
            blast_radius=5,
        )
        
        result = finding.to_dict()
        
        assert result["type"] == "high_confidence_link"
        assert result["confidence"] == 0.85
        assert result["source"] == "env:TEST"
        assert result["blast_radius"] == 5


class TestTopFindingsSummary:
    """Tests for TopFindingsSummary."""
    
    def test_get_top_n(self):
        """Test getting top N findings."""
        findings = [
            Finding(
                type=FindingType.HIGH_CONFIDENCE_LINK,
                title="Low",
                description="",
                confidence=0.5,
                interest_score=1.0,
            ),
            Finding(
                type=FindingType.AMBIGUOUS_MATCH,
                title="High",
                description="",
                confidence=0.5,
                interest_score=5.0,
            ),
            Finding(
                type=FindingType.MISSING_PROVIDER,
                title="Medium",
                description="",
                confidence=0.5,
                interest_score=3.0,
            ),
        ]
        
        summary = TopFindingsSummary(findings=findings)
        top = summary.get_top_n(2)
        
        assert len(top) == 2
        assert top[0].title == "High"
        assert top[1].title == "Medium"
    
    def test_to_dict(self):
        """Test summary serialization."""
        summary = TopFindingsSummary(
            total_connections=10,
            high_confidence_count=5,
            medium_confidence_count=3,
            low_confidence_count=2,
        )
        
        result = summary.to_dict()
        
        assert result["total_connections"] == 10
        assert result["high_confidence_count"] == 5


class TestTopFindingsExtractor:
    """Tests for TopFindingsExtractor."""
    
    @pytest.fixture
    def mock_graph(self):
        """Create a mock graph for testing."""
        graph = MagicMock()
        
        # Create test nodes
        env_node = Node(
            id="env:DATABASE_URL",
            name="DATABASE_URL",
            type=NodeType.ENV_VAR,
            path="config.py"
        )
        infra_node = Node(
            id="infra:output:database_url",
            name="database_url",
            type=NodeType.INFRA_RESOURCE,
            path="terraform/rds.tf"
        )
        
        # Create test edge
        edge = Edge(
            source_id="env:DATABASE_URL",
            target_id="infra:output:database_url",
            type=RelationshipType.READS,
            confidence=0.85,
        )
        
        graph.iter_edges.return_value = [edge]
        graph.get_node.side_effect = lambda id: {
            "env:DATABASE_URL": env_node,
            "infra:output:database_url": infra_node,
        }.get(id)
        graph.get_nodes_by_type.return_value = [env_node]
        graph.get_out_edges.return_value = [edge]
        graph.get_descendants.return_value = set()
        
        return graph
    
    def test_extract_finds_connections(self, mock_graph):
        """Test that extractor finds connections."""
        extractor = TopFindingsExtractor(mock_graph)
        summary = extractor.extract()
        
        assert summary.total_connections == 1
        assert summary.high_confidence_count == 1
        assert len(summary.findings) >= 1
    
    def test_extract_calculates_interest_score(self, mock_graph):
        """Test that interest scores are calculated."""
        extractor = TopFindingsExtractor(mock_graph)
        summary = extractor.extract()
        
        # Should have findings with interest scores
        findings = summary.findings
        assert all(f.interest_score >= 0 for f in findings)
