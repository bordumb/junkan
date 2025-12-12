"""
Scan Summary Formatter.

Creates beautiful, manager-readable summaries of scan results.
"""

from typing import List, Optional

from rich.console import Console
from rich.panel import Panel

from ...analysis.top_findings import Finding, FindingType, TopFindingsSummary
from ...core.mode import ScanMode


class ScanSummaryFormatter:
    """
    Formats scan results into beautiful, readable output.
    """

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def format_summary(
        self,
        nodes_found: int,
        edges_found: int,
        stitched_count: int,
        files_parsed: int,
        duration_sec: float,
        mode: ScanMode,
        findings_summary: Optional[TopFindingsSummary] = None,
        pack_name: Optional[str] = None,
    ) -> None:
        """
        Print a complete, manager-readable scan summary.
        """
        # Header
        self.console.print()
        # FIX: Lowercase 'complete' to match integration tests
        self.console.print("✨ [bold green]Scan complete![/bold green]")
        self.console.print()

        # Architecture Overview Box
        self._print_overview_box(
            nodes_found,
            edges_found,
            stitched_count,
            mode,
            pack_name,
        )

        # Connection Quality Breakdown
        if findings_summary and findings_summary.total_connections > 0:
            self._print_quality_breakdown(findings_summary)

        # Top Findings
        if findings_summary and findings_summary.findings:
            self._print_top_findings(findings_summary.get_top_n(5))

        # Next Steps
        self._print_next_steps(mode, stitched_count)

        # Footer stats
        self.console.print()
        self.console.print(f"[dim]Parsed {files_parsed} files in {duration_sec:.1f}s[/dim]")

    def _print_overview_box(
        self,
        nodes: int,
        edges: int,
        stitched: int,
        mode: ScanMode,
        pack_name: Optional[str],
    ) -> None:
        """Print the architecture overview box."""
        # Count by type (simplified - in real impl would query graph)
        lines = []
        lines.append("[bold]YOUR ARCHITECTURE AT A GLANCE[/bold]")
        lines.append("")
        lines.append(f"  📦 Total Artifacts Discovered:    [cyan]{nodes}[/cyan]")
        lines.append(f"  🔗 Cross-Domain Connections:      [cyan]{stitched}[/cyan]")
        lines.append(f"  📊 Total Relationships:           [cyan]{edges}[/cyan]")
        lines.append("")

        mode_color = "yellow" if mode == ScanMode.DISCOVERY else "green"
        mode_label = "Discovery" if mode == ScanMode.DISCOVERY else "Enforcement"
        lines.append(f"  Mode: [{mode_color}]{mode_label}[/{mode_color}]")

        if pack_name:
            lines.append(f"  Pack: [cyan]{pack_name}[/cyan]")

        content = "\n".join(lines)
        self.console.print(Panel(content, border_style="blue", padding=(1, 2)))

    def _print_quality_breakdown(self, summary: TopFindingsSummary) -> None:
        """Print connection quality breakdown."""
        self.console.print()
        self.console.print("[bold]📊 Connection Quality:[/bold]")

        total = summary.total_connections
        if total == 0:
            return

        high_pct = (summary.high_confidence_count / total) * 100
        med_pct = (summary.medium_confidence_count / total) * 100
        low_pct = (summary.low_confidence_count / total) * 100

        self.console.print(
            f"   [green]✅ High confidence (>70%):[/green]   "
            f"{summary.high_confidence_count} ({high_pct:.0f}%) - likely real"
        )
        self.console.print(
            f"   [yellow]⚠️  Medium confidence (40-70%):[/yellow] "
            f"{summary.medium_confidence_count} ({med_pct:.0f}%) - review recommended"
        )
        self.console.print(
            f"   [red]❓ Low confidence (<40%):[/red]    "
            f"{summary.low_confidence_count} ({low_pct:.0f}%) - may be false positives"
        )

        if summary.ambiguous_count > 0:
            self.console.print(
                f"   [magenta]🔀 Ambiguous matches:[/magenta]        "
                f"{summary.ambiguous_count} - have multiple possible targets"
            )

        if summary.missing_providers > 0:
            self.console.print(
                f"   [dim]📭 Missing providers:[/dim]         "
                f"{summary.missing_providers} env vars with no infra source"
            )

    def _print_top_findings(self, findings: List[Finding]) -> None:
        """Print top findings section."""
        if not findings:
            return

        self.console.print()
        self.console.print("[bold]🎯 KEY FINDINGS:[/bold]")
        self.console.print()

        for i, finding in enumerate(findings, 1):
            self._print_single_finding(i, finding)

    def _print_single_finding(self, index: int, finding: Finding) -> None:
        """Print a single finding with appropriate formatting."""
        # Icon based on type
        icons = {
            FindingType.HIGH_CONFIDENCE_LINK: "✅",
            FindingType.AMBIGUOUS_MATCH: "⚠️",
            FindingType.MISSING_PROVIDER: "❌",
            FindingType.CROSS_DOMAIN_CHAIN: "🔗",
            FindingType.HIGH_BLAST_RADIUS: "💥",
            FindingType.POTENTIAL_RISK: "❓",
        }
        icon = icons.get(finding.type, "•")

        # Color based on confidence
        if finding.confidence >= 0.7:
            conf_color = "green"
        elif finding.confidence >= 0.4:
            conf_color = "yellow"
        else:
            conf_color = "red"

        # Title line
        self.console.print(f"  {index}. [bold]{finding.title}[/bold]")

        # Source file if available
        if finding.source_node and finding.source_node.path:
            self.console.print(f"     [dim]File: {finding.source_node.path}[/dim]")

        # Connection details
        if finding.target_node:
            conf_pct = int(finding.confidence * 100)
            self.console.print(f"     └── {icon} Linked to: [cyan]{finding.target_node.id}[/cyan]")
            self.console.print(f"         Confidence: [{conf_color}]{conf_pct}%[/{conf_color}]")
        elif finding.type == FindingType.MISSING_PROVIDER:
            self.console.print(
                f"     └── {icon} [yellow]NO MATCH FOUND[/yellow] - "
                f"This env var has no infrastructure provider"
            )
            self.console.print(
                "         [dim]💡 Is this set manually? Consider documenting.[/dim]"
            )

        # Ambiguity warning
        if finding.metadata.get("is_ambiguous"):
            match_count = finding.metadata.get("match_count", 2)
            self.console.print(
                f"         [magenta]⚠️  Matches {match_count} possible targets - "
                f"consider more specific naming[/magenta]"
            )

        # Blast radius if significant
        if finding.blast_radius > 5:
            self.console.print(
                f"         [red]💥 High impact: {finding.blast_radius} "
                f"downstream dependencies[/red]"
            )

        self.console.print()

    def _print_next_steps(self, mode: ScanMode, stitched: int) -> None:
        """Print recommended next steps."""
        self.console.print("[bold]📋 Next Steps:[/bold]")

        if stitched == 0:
            self.console.print("   [yellow]No cross-domain connections found.[/yellow]")
            self.console.print(
                "   This could mean your code doesn't use environment variables, "
                "or jnkn needs tuning."
            )
            self.console.print(
                "   Try: [cyan]jnkn scan --verbose[/cyan] to see what's being parsed."
            )
            return

        if mode == ScanMode.DISCOVERY:
            self.console.print(
                "   1. Run [cyan]jnkn review[/cyan] to validate connections (~5 min)"
            )
            self.console.print(
                "   2. Run [cyan]jnkn blast <variable>[/cyan] to see impact of changes"
            )
            self.console.print("   3. Add [cyan]jnkn check[/cyan] to your CI pipeline")
        else:
            self.console.print(
                "   1. Run [cyan]jnkn blast <variable>[/cyan] to see impact of changes"
            )
            self.console.print("   2. Run [cyan]jnkn diff main HEAD[/cyan] to analyze PR impact")
            self.console.print(
                "   3. Use [cyan]jnkn scan --mode discovery[/cyan] to find new connections"
            )


def format_scan_summary(
    console: Console,
    nodes_found: int,
    edges_found: int,
    stitched_count: int,
    files_parsed: int,
    duration_sec: float,
    mode: ScanMode,
    findings_summary: Optional[TopFindingsSummary] = None,
    pack_name: Optional[str] = None,
) -> None:
    """
    Convenience function to format and print scan summary.
    """
    formatter = ScanSummaryFormatter(console)
    formatter.format_summary(
        nodes_found=nodes_found,
        edges_found=edges_found,
        stitched_count=stitched_count,
        files_parsed=files_parsed,
        duration_sec=duration_sec,
        mode=mode,
        findings_summary=findings_summary,
        pack_name=pack_name,
    )
