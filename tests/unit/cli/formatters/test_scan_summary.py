"""
Tests for Scan Summary Formatter.
"""

import pytest
from unittest.mock import MagicMock, call
from rich.console import Console
from rich.panel import Panel

from jnkn.cli.formatters.scan_summary import ScanSummaryFormatter, format_scan_summary
from jnkn.core.mode import ScanMode
from jnkn.analysis.top_findings import TopFindingsSummary, Finding, FindingType
from jnkn.core.types import Node, NodeType

class TestScanSummaryFormatter:
    @pytest.fixture
    def mock_console(self):
        return MagicMock(spec=Console)

    @pytest.fixture
    def formatter(self, mock_console):
        return ScanSummaryFormatter(mock_console)

    def test_format_summary_basic(self, formatter, mock_console):
        formatter.format_summary(
            nodes_found=10,
            edges_found=5,
            stitched_count=2,
            files_parsed=20,
            duration_sec=1.5,
            mode=ScanMode.DISCOVERY
        )
        
        # Verify basic stats printed
        assert mock_console.print.called
        
        found_scan_complete = False
        found_discovery_mode = False

        # Iterate through all print calls to find specific content types
        for call_args in mock_console.print.call_args_list:
            args, _ = call_args
            if not args:
                continue
            
            arg = args[0]
            
            # Check for simple string messages (like the header)
            if isinstance(arg, str):
                if "Scan complete" in arg:
                    found_scan_complete = True
            
            # Check for Rich Panels (architecture overview)
            # The Panel object holds the text in .renderable
            if isinstance(arg, Panel):
                content = str(arg.renderable)
                if "Discovery" in content:
                    found_discovery_mode = True

        assert found_scan_complete, "Header 'Scan complete' not found in output"
        assert found_discovery_mode, "Mode 'Discovery' not found inside the Overview Panel"

    def test_format_summary_with_pack(self, formatter, mock_console):
        formatter.format_summary(
            nodes_found=10, edges_found=5, stitched_count=2,
            files_parsed=20, duration_sec=1.5,
            mode=ScanMode.ENFORCEMENT,
            pack_name="django-aws"
        )
        
        # Should see pack name in the Overview Panel
        # We search through calls robustly instead of hardcoding indices
        panel_found = False
        
        for call_args in mock_console.print.call_args_list:
            args, _ = call_args
            # Skip empty print calls (newlines) which cause IndexError on args[0]
            if not args:
                continue
            
            arg = args[0]
            # Check if this printed item is the Panel we are looking for
            if isinstance(arg, Panel):
                # Rich Panel stores content in .renderable
                panel_content = str(arg.renderable)
                if "django-aws" in panel_content and "Enforcement" in panel_content:
                    panel_found = True
                    break
        
        assert panel_found, "Overview Panel containing 'django-aws' and 'Enforcement' was not found in console output"

    def test_quality_breakdown(self, formatter, mock_console):
        summary = TopFindingsSummary(
            total_connections=100,
            high_confidence_count=80,
            medium_confidence_count=15,
            low_confidence_count=5,
            ambiguous_count=2,
            missing_providers=1
        )
        
        formatter._print_quality_breakdown(summary)
        
        calls = [str(c) for c in mock_console.print.mock_calls]
        assert any("80 (80%)" in c for c in calls) # High conf
        assert any("Ambiguous matches" in c for c in calls)
        assert any("Missing providers" in c for c in calls)

    def test_top_findings_output(self, formatter, mock_console):
        node = Node(id="n1", name="node1", type=NodeType.ENV_VAR, path="app.py")
        finding = Finding(
            type=FindingType.HIGH_CONFIDENCE_LINK,
            title="Test Finding",
            description="Desc",
            confidence=0.9,
            interest_score=5.0,
            source_node=node,
            blast_radius=10,
            metadata={"is_ambiguous": True, "match_count": 3}
        )
        
        formatter._print_top_findings([finding])
        
        calls = [str(c) for c in mock_console.print.mock_calls]
        assert any("Test Finding" in c for c in calls)
        assert any("app.py" in c for c in calls)
        assert any("High impact: 10" in c for c in calls)
        assert any("Matches 3 possible targets" in c for c in calls)

    def test_next_steps_discovery_no_stitch(self, formatter, mock_console):
        formatter._print_next_steps(ScanMode.DISCOVERY, stitched=0)
        calls = [str(c) for c in mock_console.print.mock_calls]
        assert any("No cross-domain connections found" in c for c in calls)

    def test_next_steps_discovery_with_stitch(self, formatter, mock_console):
        formatter._print_next_steps(ScanMode.DISCOVERY, stitched=5)
        calls = [str(c) for c in mock_console.print.mock_calls]
        assert any("jnkn review" in c for c in calls)

    def test_next_steps_enforcement(self, formatter, mock_console):
        formatter._print_next_steps(ScanMode.ENFORCEMENT, stitched=5)
        calls = [str(c) for c in mock_console.print.mock_calls]
        assert any("jnkn diff" in c for c in calls)

    def test_global_wrapper(self, mock_console):
        # Smoke test for the global function
        format_scan_summary(mock_console, 0, 0, 0, 0, 0.0, ScanMode.DISCOVERY)
        assert mock_console.print.called