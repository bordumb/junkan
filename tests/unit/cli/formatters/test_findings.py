"""
Tests for Findings Formatter.
"""

import pytest
from unittest.mock import MagicMock
from rich.console import Console
from rich.table import Table

from jnkn.cli.formatters.findings import FindingsFormatter, format_findings
from jnkn.analysis.top_findings import Finding, FindingType
from jnkn.core.types import Node, NodeType

class TestFindingsFormatter:
    @pytest.fixture
    def mock_console(self):
        return MagicMock(spec=Console)

    @pytest.fixture
    def formatter(self, mock_console):
        return FindingsFormatter(mock_console)

    @pytest.fixture
    def sample_finding(self):
        src = Node(id="s", name="source", type=NodeType.ENV_VAR, path="s.py")
        tgt = Node(id="t", name="target", type=NodeType.INFRA_RESOURCE, path="t.tf")
        return Finding(
            type=FindingType.HIGH_CONFIDENCE_LINK,
            title="Connection",
            description="Desc",
            confidence=0.8,
            interest_score=1.0,
            source_node=src,
            target_node=tgt,
            blast_radius=5
        )

    def test_format_as_table(self, formatter, mock_console, sample_finding):
        findings = [
            sample_finding,
            # Add a low confidence, ambiguous finding
            Finding(
                type=FindingType.AMBIGUOUS_MATCH,
                title="Ambiguous",
                description="Desc",
                confidence=0.3,
                interest_score=1.0,
                source_node=Node(id="a", name="amb", type=NodeType.ENV_VAR),
                metadata={"is_ambiguous": True}
            )
        ]
        
        formatter.format_as_table(findings)
        
        assert mock_console.print.called
        # Check that a Table object was passed
        args, _ = mock_console.print.call_args
        assert isinstance(args[0], Table)
        
        # We can inspect the table object to verify rows were added
        table = args[0]
        assert table.row_count == 2

    def test_format_detailed(self, formatter, mock_console, sample_finding):
        formatter.format_detailed(sample_finding)
        
        calls = [str(c) for c in mock_console.print.mock_calls]
        
        assert any("Connection" in c for c in calls) # Title
        assert any("source" in c for c in calls)     # Source name
        assert any("target" in c for c in calls)     # Target name
        assert any("80%" in c for c in calls)        # Confidence
        assert any("Blast Radius" in c for c in calls)

    def test_global_wrapper_table(self, mock_console, sample_finding):
        format_findings(mock_console, [sample_finding], detailed=False)
        # Should print table
        args, _ = mock_console.print.call_args
        assert isinstance(args[0], Table)

    def test_global_wrapper_detailed(self, mock_console, sample_finding):
        format_findings(mock_console, [sample_finding], detailed=True)
        # Should print detailed text strings, not a table
        args, _ = mock_console.print.call_args
        assert not isinstance(args[0], Table)