"""
Action Command - The Configurable CI/CD Runner.

This command encapsulates the entire CI workflow with support for
custom failure thresholds and scan configurations. It is designed to be
called by the GitHub Action workflow.
"""

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

import click
import click.testing
from rich.console import Console

from ...core.stitching import Stitcher
from ...core.storage.sqlite import SQLiteStorage
from ...parsing.engine import ScanConfig, create_default_engine

# Initialize console for pretty logs in CI
console = Console(stderr=True)

# Unique marker to identify comments posted by this tool
SIGNATURE = ""


@click.command()
@click.option("--token", required=True, help="GitHub Token")
@click.option("--base", default="origin/main", help="Base ref")
@click.option("--head", default="HEAD", help="Head ref")
@click.option(
    "--fail-on",
    default="critical",
    type=click.Choice(["critical", "high", "medium", "none"], case_sensitive=False),
    help="Severity level to fail the build on",
)
@click.option("--scan-dir", default=".", help="Directory to scan")
@click.option("--config", "config_path", default=".jnkn/config.yaml", help="Path to config file")
def action(token: str, base: str, head: str, fail_on: str, scan_dir: str, config_path: str):
    """Run the complete CI/CD impact analysis workflow."""

    # 1. SETUP: Paths and Config
    work_dir = Path(scan_dir).absolute()
    db_path = work_dir / ".jnkn" / "jnkn.db"

    console.print("🚀 [bold blue]Jnkn Action[/bold blue]")
    console.print(f"   Scan Dir: {work_dir}")
    console.print(f"   Failure Threshold: {fail_on}")

    # 2. SCAN: Build the graph
    console.print("\n[bold]1. Building Dependency Graph...[/bold]")
    db_path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_default_engine()
    storage = SQLiteStorage(db_path)
    storage.clear()  # Clean build for CI consistency

    # Load user config if it exists (placeholder logic for now)
    scan_config = ScanConfig(root_dir=work_dir, incremental=False)

    # Run Scan
    scan_result = engine.scan_and_store(storage, scan_config)
    if scan_result.is_err():
        console.print(f"❌ [red]Scan failed:[/red] {scan_result.unwrap_err().message}")
        sys.exit(1)

    stats = scan_result.unwrap()
    console.print(f"   Parsed {stats.files_scanned} files.")

    # Stitch
    graph = storage.load_graph()
    if graph.node_count == 0:
        console.print("⚠️  [yellow]Graph is empty. Check scan-dir or .jnknignore.[/yellow]")
    else:
        stitcher = Stitcher()
        new_edges = stitcher.stitch(graph)
        storage.save_edges_batch(new_edges)
        console.print(f"   Stitched {len(new_edges)} cross-domain links.")

    storage.close()

    # 3. CHECK: Analyze Diffs
    console.print(f"\n[bold]2. Analyzing Impact ({base} -> {head})...[/bold]")

    # Reuse the check command logic via CLI invocation to ensure consistency
    from .check import check as check_cmd

    # Using the module-level import allows this to be patched reliably in tests
    runner = click.testing.CliRunner()

    # Invoke 'check' and capture JSON output
    result = runner.invoke(check_cmd, ["--git-diff", base, head, "--json"])

    # The 'check' command might exit with 1 if violations found, which is fine
    # We only care if it crashed (produced no JSON)
    output_str = result.output.strip()
    if not output_str.startswith("{"):
        console.print(f"❌ [red]Check command failed internally:[/red]\n{result.output}")
        sys.exit(1)

    try:
        response = json.loads(output_str)
        report = response.get("data", {})
        if not report:
            raise ValueError("No data in check response")
    except Exception as e:
        console.print(f"❌ [red]Failed to parse check results:[/red] {e}")
        console.print(output_str)
        sys.exit(1)

    # 4. REPORT: Generate Markdown & Post Comment
    comment_body = _generate_markdown(report, fail_on)
    _post_to_github(token, comment_body)

    # 5. GATE: Determine Exit Code
    should_fail = False

    critical = report.get("critical_count", 0)
    high = report.get("high_count", 0)

    if fail_on == "critical" and critical > 0:
        should_fail = True
        console.print(f"❌ [red]Blocking build: {critical} critical violations found.[/red]")
    elif fail_on == "high" and (critical > 0 or high > 0):
        should_fail = True
        console.print(
            f"❌ [red]Blocking build: {critical} critical, {high} high violations found.[/red]"
        )
    elif fail_on == "medium":
        pass

    if should_fail:
        sys.exit(1)

    console.print("✅ [green]Check passed![/green]")
    sys.exit(0)


def _generate_markdown(report: Dict[str, Any], fail_threshold: str) -> str:
    """Generate a GitHub-flavored markdown report."""
    stats = {
        "critical": report.get("critical_count", 0),
        "high": report.get("high_count", 0),
        "files": report.get("changed_files_count", 0),
    }

    is_blocked = False
    if fail_threshold == "critical" and stats["critical"] > 0:
        is_blocked = True
    if fail_threshold == "high" and (stats["critical"] > 0 or stats["high"] > 0):
        is_blocked = True

    emoji = "🚫" if is_blocked else "⚠️" if (stats["critical"] + stats["high"] > 0) else "✅"
    title = "Impact Check Failed" if is_blocked else "Impact Analysis"

    body = f"{SIGNATURE}\n### {emoji} Jnkn {title}\n\n"
    body += "| Metric | Count |\n|---|---|\n"
    body += f"| 📄 Files Changed | {stats['files']} |\n"
    body += f"| 🔴 Critical Risks | {stats['critical']} |\n"
    body += f"| 🟠 High Risks | {stats['high']} |\n\n"

    violations = report.get("violations", [])
    if violations:
        body += "#### 🚨 Violations\n"
        body += "| Severity | Rule | Message |\n|---|---|---|\n"
        for v in violations:
            sev = v.get("severity", "unknown")
            msg = v.get("message", "")
            rule = v.get("rule", "")
            icon = "🔴" if sev == "critical" else "🟠"
            body += f"| {icon} {sev} | `{rule}` | {msg} |\n"
    elif stats["critical"] == 0 and stats["high"] == 0:
        body += "✨ No semantic breaking changes detected. Safe to merge!\n"

    body += "\n"
    return body


def _post_to_github(token: str, body: str):
    """Post comment to GitHub PR using standard library only."""
    repo = os.getenv("GITHUB_REPOSITORY")
    event_path = os.getenv("GITHUB_EVENT_PATH")

    if not repo or not event_path:
        console.print("⚠️  Not running in GitHub Actions context. Skipping comment.")
        return

    try:
        with open(event_path) as f:
            event = json.load(f)
            issue_number = event.get("pull_request", {}).get("number")
            if not issue_number:
                console.print("⚠️  No PR number found in event. Skipping comment.")
                return
    except Exception as e:
        console.print(f"⚠️  Failed to read event data: {e}")
        return

    api_url = f"https://api.github.com/repos/{repo}/issues/{issue_number}/comments"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "jnkn-action",
    }

    comment_id = None
    # 1. Try to find existing comment
    try:
        req = urllib.request.Request(api_url, headers=headers)
        with urllib.request.urlopen(req) as resp:
            comments = json.load(resp)
            for c in comments:
                if SIGNATURE in c.get("body", ""):
                    comment_id = c["id"]
                    break
    except Exception as e:
        # Don't fail the build if listing fails, just try to post new
        console.print(f"[dim]⚠️  Failed to list comments: {e}[/dim]")

    # 2. Prepare Request
    data = json.dumps({"body": body}).encode("utf-8")

    if comment_id:
        url = f"{api_url}/{comment_id}"
        method = "PATCH"
        action = "Updated"
    else:
        url = api_url
        method = "POST"
        action = "Posted"

    console.print(f"[dim]Attempting to {method} comment to: {url}[/dim]")

    # 3. Execute
    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req) as resp:
            if resp.status in (200, 201):
                console.print(f"✅ [green]{action} PR comment[/green]")
            else:
                console.print(f"⚠️  Failed to post comment: HTTP {resp.status}")
    except urllib.error.HTTPError as e:
        console.print(f"❌ [red]HTTP Error {e.code}: {e.reason}[/red]")
        console.print(f"   [dim]URL: {url}[/dim]")
        if e.code == 404 and method == "POST":
            console.print(
                "   [yellow]Hint: A 404 on POST usually means the GITHUB_TOKEN lacks 'write' permission.[/yellow]"
            )
            console.print("   [yellow]Ensure your workflow includes:[/yellow]")
            console.print("   [yellow]permissions:[/yellow]")
            console.print("   [yellow]  pull-requests: write[/yellow]")
        elif e.code == 404:
            console.print("   [yellow]Hint: The PR or Issue might not exist or be accessible.[/yellow]")
    except Exception as e:
        console.print(f"❌ [red]Error posting comment: {e}[/red]")