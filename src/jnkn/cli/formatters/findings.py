"""
Findings Formatter.

Formats individual findings and finding lists for CLI output.
"""

from typing import List

from rich.console import Console
from rich.table import Table

from ...analysis.top_findings import Finding


class FindingsFormatter:
    """
    Formats findings for display.
    """

    def __init__(self, console: Console | None = None):
        self.console = console or Console()

    def format_as_table(self, findings: List[Finding]) -> None:
        """Format findings as a table."""
        table = Table(title="Findings")

        table.add_column("#", style="dim", width=3)
        table.add_column("Type", style="cyan")
        table.add_column("Source", style="green")
        table.add_column("Target", style="yellow")
        table.add_column("Confidence", justify="right")
        table.add_column("Status")

        for i, finding in enumerate(findings, 1):
            source = finding.source_node.name if finding.source_node else "-"
            target = finding.target_node.name if finding.target_node else "-"
            conf = f"{int(finding.confidence * 100)}%"

            # Status indicator
            if finding.confidence >= 0.7:
                status = "[green]✅ High[/green]"
            elif finding.confidence >= 0.4:
                status = "[yellow]⚠️ Medium[/yellow]"
            else:
                status = "[red]❓ Low[/red]"

            if finding.metadata.get("is_ambiguous"):
                status = "[magenta]🔀 Ambiguous[/magenta]"

            table.add_row(
                str(i),
                finding.type.value.replace("_", " ").title(),
                source,
                target,
                conf,
                status,
            )

        self.console.print(table)

    def format_detailed(self, finding: Finding) -> None:
        """Format a single finding with full details."""
        self.console.print()
        self.console.print(f"[bold]{finding.title}[/bold]")
        self.console.print(f"[dim]Type: {finding.type.value}[/dim]")
        self.console.print()
        self.console.print(finding.description)

        if finding.source_node:
            self.console.print()
            self.console.print("[bold]Source:[/bold]")
            self.console.print(f"  ID: {finding.source_node.id}")
            self.console.print(f"  Name: {finding.source_node.name}")
            self.console.print(f"  File: {finding.source_node.path}")

        if finding.target_node:
            self.console.print()
            self.console.print("[bold]Target:[/bold]")
            self.console.print(f"  ID: {finding.target_node.id}")
            self.console.print(f"  Name: {finding.target_node.name}")
            self.console.print(f"  File: {finding.target_node.path}")

        self.console.print()
        self.console.print(f"[bold]Confidence:[/bold] {int(finding.confidence * 100)}%")
        self.console.print(f"[bold]Interest Score:[/bold] {finding.interest_score:.1f}")

        if finding.blast_radius > 0:
            self.console.print(f"[bold]Blast Radius:[/bold] {finding.blast_radius} nodes")


def format_findings(
    console: Console,
    findings: List[Finding],
    detailed: bool = False,
) -> None:
    """
    Convenience function to format and print findings.
    """
    formatter = FindingsFormatter(console)

    if detailed and len(findings) == 1:
        formatter.format_detailed(findings[0])
    else:
        formatter.format_as_table(findings)
