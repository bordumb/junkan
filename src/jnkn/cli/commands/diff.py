"""
Diff Command - Semantic Diff Analysis for Data Pipelines.

Analyzes what actually changed between two git refs, not just which files changed.

Usage:
    # Compare against main
    jnkn diff main HEAD
    
    # Compare specific branches
    jnkn diff feature-branch main
    
    # Output as JSON
    jnkn diff main HEAD --format json
    
    # Only show breaking changes
    jnkn diff main HEAD --breaking-only
"""

import json
import sys
from pathlib import Path
from typing import Optional

import click

# Import the analyzer
try:
    from jnkn.analysis.diff_analyzer import ChangeType, DiffAnalyzer, DiffReport
except ImportError:
    # For standalone usage
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))
    from diff_analyzer import ChangeType, DiffAnalyzer, DiffReport


@click.command()
@click.argument("base_ref", default="main")
@click.argument("head_ref", default="HEAD")
@click.option("--repo", "-r", default=".", help="Path to git repository")
@click.option("--format", "output_format", type=click.Choice(["text", "json", "markdown"]),
              default="text", help="Output format")
@click.option("--output", "-o", type=click.Path(), help="Write output to file")
@click.option("--breaking-only", is_flag=True, help="Only show breaking changes")
@click.option("--columns-only", is_flag=True, help="Only show column changes")
@click.option("--fail-on-breaking", is_flag=True, help="Exit 1 if breaking changes found")
@click.option("--quiet", "-q", is_flag=True, help="Minimal output")
def diff(
    base_ref: str,
    head_ref: str,
    repo: str,
    output_format: str,
    output: str | None,
    breaking_only: bool,
    columns_only: bool,
    fail_on_breaking: bool,
    quiet: bool,
):
    """
    Analyze semantic changes between git refs.
    
    Instead of just showing which files changed, this command analyzes
    WHAT changed in terms of columns, tables, and lineage.
    
    \b
    Examples:
        # Basic usage
        jnkn diff main HEAD
        
        # Compare branches
        jnkn diff feature-x origin/main
        
        # CI/CD usage - fail if breaking changes
        jnkn diff origin/main HEAD --fail-on-breaking
        
        # Generate markdown report
        jnkn diff main HEAD --format markdown > CHANGES.md
    
    \b
    Exit Codes:
        0 - Success (no breaking changes, or --fail-on-breaking not set)
        1 - Breaking changes detected (with --fail-on-breaking)
        2 - Error during analysis
    """
    try:
        analyzer = DiffAnalyzer(repo_path=repo)
        report = analyzer.analyze(base_ref, head_ref)
    except Exception as e:
        if not quiet:
            click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        sys.exit(2)

    # Filter if requested
    if breaking_only:
        report = _filter_breaking_only(report)

    if columns_only:
        report.lineage_changes = []
        report.transform_changes = []
        report.table_changes = []

    # Output
    if output_format == "json":
        result = json.dumps(report.to_dict(), indent=2)
    elif output_format == "markdown":
        result = report.to_markdown()
    else:
        result = _format_text(report, quiet)

    if output:
        with open(output, "w") as f:
            f.write(result)
        if not quiet:
            click.echo(f"Report written to {output}")
    else:
        click.echo(result)

    # Exit code
    if fail_on_breaking and report.has_breaking_changes:
        sys.exit(1)

    sys.exit(0)


def _filter_breaking_only(report: DiffReport) -> DiffReport:
    """Filter report to only include breaking changes."""
    report.column_changes = [
        c for c in report.column_changes
        if c.change_type == ChangeType.REMOVED
    ]
    report.table_changes = [
        t for t in report.table_changes
        if t.change_type == ChangeType.REMOVED
    ]
    report.lineage_changes = [
        l for l in report.lineage_changes
        if l.change_type == ChangeType.REMOVED
    ]
    return report


def _format_text(report: DiffReport, quiet: bool) -> str:
    """Format report as colored text."""
    lines = []

    if not quiet:
        lines.append("")
        lines.append(click.style("📊 Diff Analysis", bold=True))
        lines.append(click.style(f"   {report.base_ref} → {report.head_ref}", dim=True))
        lines.append("")

    # Summary
    s = report.summary
    if not quiet:
        lines.append(click.style("Summary:", bold=True))
        lines.append(f"  Files changed:      {s['files_changed']}")
        lines.append(f"  Columns added:      {click.style(str(s['columns_added']), fg='green')}")
        lines.append(f"  Columns removed:    {click.style(str(s['columns_removed']), fg='red')}")
        lines.append(f"  Lineage changed:    {s['lineage_mappings_changed']}")
        lines.append(f"  Transforms changed: {s['transforms_changed']}")
        lines.append("")

    # Breaking changes warning
    if report.has_breaking_changes:
        lines.append(click.style("⚠️  BREAKING CHANGES DETECTED", fg="red", bold=True))
        lines.append("")

        removed_cols = [c for c in report.column_changes if c.change_type == ChangeType.REMOVED]
        if removed_cols:
            lines.append(click.style("Removed Columns:", fg="red"))
            for c in removed_cols:
                table = f"{c.table}." if c.table else ""
                lines.append(f"  🗑️  {table}{c.column} ({c.context}) in {c.file_path}")
            lines.append("")

    # Column changes
    if report.column_changes and not quiet:
        lines.append(click.style("Column Changes:", bold=True))

        added = [c for c in report.column_changes if c.change_type == ChangeType.ADDED]
        removed = [c for c in report.column_changes if c.change_type == ChangeType.REMOVED]
        modified = [c for c in report.column_changes if c.change_type == ChangeType.MODIFIED]

        for c in added:
            lines.append(click.style(f"  ➕ {c.column} ({c.context})", fg="green"))
        for c in removed:
            lines.append(click.style(f"  🗑️  {c.column} ({c.context})", fg="red"))
        for c in modified:
            lines.append(click.style(f"  ✏️  {c.column} ({c.context})", fg="yellow"))

        lines.append("")

    # Lineage changes
    if report.lineage_changes and not quiet:
        lines.append(click.style("Lineage Changes:", bold=True))
        for lc in report.lineage_changes:
            if lc.change_type == ChangeType.ADDED:
                lines.append(click.style(f"  ➕ {lc.output_column} ← {lc.new_sources}", fg="green"))
            elif lc.change_type == ChangeType.REMOVED:
                lines.append(click.style(f"  🗑️  {lc.output_column} ← {lc.old_sources}", fg="red"))
            else:
                lines.append(click.style(f"  ✏️  {lc.output_column}: {lc.old_sources} → {lc.new_sources}", fg="yellow"))
        lines.append("")

    # Transform changes
    if report.transform_changes and not quiet:
        lines.append(click.style("Transform Changes:", bold=True))
        for tc in report.transform_changes:
            if tc.change_type == ChangeType.MODIFIED:
                lines.append(click.style(f"  ✏️  {tc.column}: {tc.old_transform} → {tc.new_transform}", fg="yellow"))
            elif tc.change_type == ChangeType.ADDED:
                lines.append(click.style(f"  ➕ {tc.column}: {tc.new_transform}", fg="green"))
            else:
                lines.append(click.style(f"  🗑️  {tc.column}: {tc.old_transform}", fg="red"))
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    diff()
