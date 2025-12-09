"""
Check Command - CI/CD Gate for Pre-Merge Impact Analysis.

This command is designed to run in CI pipelines to:
1. Parse changed files from a PR/diff
2. Enrich with OpenLineage runtime data
3. Calculate blast radius of changes
4. Apply policy rules (critical tables, required approvals)
5. Exit with appropriate code (0=pass, 1=blocked, 2=warn)

Usage:
    # Basic check
    jnkn check --diff changes.txt
    
    # With OpenLineage enrichment
    jnkn check --diff changes.txt --openlineage-url http://marquez:5000
    
    # With policy enforcement
    jnkn check --diff changes.txt --policy policy.yaml --fail-if-critical
    
    # GitHub Actions integration
    jnkn check --github-pr 123 --repo owner/repo
"""

import click
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# Data Models
# =============================================================================

class Severity(Enum):
    """Impact severity levels."""
    CRITICAL = "critical"  # Blocks PR
    HIGH = "high"          # Requires approval
    MEDIUM = "medium"      # Warning
    LOW = "low"            # Info only


class CheckResult(Enum):
    """Result of the check."""
    PASS = 0       # Safe to merge
    BLOCKED = 1    # Cannot merge without override
    WARN = 2       # Can merge but with warnings


@dataclass
class ChangedFile:
    """A file that changed in the PR."""
    path: str
    change_type: str  # added, modified, deleted, renamed
    old_path: Optional[str] = None  # For renames


@dataclass
class AffectedAsset:
    """An asset affected by the changes."""
    id: str
    name: str
    asset_type: str  # table, job, dashboard, ml-model
    severity: Severity
    confidence: float
    path: List[str]  # How the change propagates
    owners: List[str] = field(default_factory=list)


@dataclass
class ColumnChange:
    """A column-level change detected."""
    column: str
    table: Optional[str]
    change_type: str  # added, removed, modified, renamed
    old_name: Optional[str] = None


@dataclass
class PolicyViolation:
    """A policy rule that was violated."""
    rule_name: str
    severity: Severity
    message: str
    affected_assets: List[str]
    required_approvers: List[str] = field(default_factory=list)


@dataclass
class CheckReport:
    """Complete report from a check run."""
    result: CheckResult
    changed_files: List[ChangedFile]
    column_changes: List[ColumnChange]
    affected_assets: List[AffectedAsset]
    violations: List[PolicyViolation]
    
    # Stats
    total_downstream: int = 0
    critical_count: int = 0
    high_count: int = 0
    
    # Metadata
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    openlineage_enriched: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result": self.result.name,
            "exit_code": self.result.value,
            "timestamp": self.timestamp,
            "summary": {
                "changed_files": len(self.changed_files),
                "column_changes": len(self.column_changes),
                "total_downstream": self.total_downstream,
                "critical_count": self.critical_count,
                "high_count": self.high_count,
            },
            "changed_files": [
                {"path": f.path, "type": f.change_type} 
                for f in self.changed_files
            ],
            "column_changes": [
                {"column": c.column, "table": c.table, "type": c.change_type}
                for c in self.column_changes
            ],
            "affected_assets": [
                {
                    "id": a.id,
                    "name": a.name,
                    "type": a.asset_type,
                    "severity": a.severity.value,
                    "confidence": a.confidence,
                    "owners": a.owners,
                }
                for a in self.affected_assets
            ],
            "violations": [
                {
                    "rule": v.rule_name,
                    "severity": v.severity.value,
                    "message": v.message,
                    "required_approvers": v.required_approvers,
                }
                for v in self.violations
            ],
            "openlineage_enriched": self.openlineage_enriched,
        }
    
    def to_markdown(self) -> str:
        """Generate markdown summary for PR comment."""
        lines = ["## 🔍 jnkn Impact Analysis", ""]
        
        # Result banner
        if self.result == CheckResult.BLOCKED:
            lines.append("### ❌ BLOCKED - Critical Impact Detected")
        elif self.result == CheckResult.WARN:
            lines.append("### ⚠️ WARNING - Review Required")
        else:
            lines.append("### ✅ PASSED - Safe to Merge")
        lines.append("")
        
        # Summary stats
        lines.append("| Metric | Count |")
        lines.append("|--------|-------|")
        lines.append(f"| Changed Files | {len(self.changed_files)} |")
        lines.append(f"| Column Changes | {len(self.column_changes)} |")
        lines.append(f"| Downstream Impact | {self.total_downstream} |")
        lines.append(f"| Critical Systems | {self.critical_count} |")
        lines.append("")
        
        # Violations
        if self.violations:
            lines.append("### Policy Violations")
            lines.append("")
            for v in self.violations:
                icon = "🚨" if v.severity == Severity.CRITICAL else "⚠️"
                lines.append(f"{icon} **{v.rule_name}**: {v.message}")
                if v.required_approvers:
                    approvers = ", ".join(v.required_approvers)
                    lines.append(f"   - Required approvers: {approvers}")
            lines.append("")
        
        # Critical assets
        critical = [a for a in self.affected_assets if a.severity == Severity.CRITICAL]
        if critical:
            lines.append("### 🚨 Critical Systems Affected")
            lines.append("")
            for a in critical:
                owners = f" (owners: {', '.join(a.owners)})" if a.owners else ""
                lines.append(f"- **{a.name}**{owners}")
            lines.append("")
        
        # Column changes
        if self.column_changes:
            lines.append("### Column Changes Detected")
            lines.append("")
            for c in self.column_changes:
                table = f" in `{c.table}`" if c.table else ""
                if c.change_type == "removed":
                    lines.append(f"- 🗑️ REMOVED: `{c.column}`{table}")
                elif c.change_type == "added":
                    lines.append(f"- ➕ ADDED: `{c.column}`{table}")
                elif c.change_type == "modified":
                    lines.append(f"- ✏️ MODIFIED: `{c.column}`{table}")
            lines.append("")
        
        # OpenLineage status
        if self.openlineage_enriched:
            lines.append("---")
            lines.append("*📊 Enriched with OpenLineage production data*")
        
        return "\n".join(lines)


# =============================================================================
# Policy Engine
# =============================================================================

@dataclass
class PolicyRule:
    """A single policy rule."""
    name: str
    pattern: str  # Regex pattern to match asset IDs
    severity: Severity
    owners: List[str] = field(default_factory=list)
    require_approval: bool = False
    notify_always: bool = False


@dataclass
class Policy:
    """Policy configuration."""
    rules: List[PolicyRule] = field(default_factory=list)
    default_severity: Severity = Severity.LOW
    block_on_critical: bool = True
    warn_on_high: bool = True


def load_policy(path: str) -> Policy:
    """Load policy from YAML file."""
    if not HAS_YAML:
        raise ImportError("PyYAML required for policy files. pip install pyyaml")
    
    with open(path) as f:
        data = yaml.safe_load(f)
    
    rules = []
    for rule_data in data.get("critical", []) + data.get("rules", []):
        severity_str = rule_data.get("severity", "high")
        severity = Severity[severity_str.upper()]
        
        rules.append(PolicyRule(
            name=rule_data.get("name", rule_data.get("pattern", "unnamed")),
            pattern=rule_data["pattern"],
            severity=severity,
            owners=rule_data.get("owners", []),
            require_approval=rule_data.get("require_approval", False),
            notify_always=rule_data.get("notify_always", False),
        ))
    
    return Policy(
        rules=rules,
        block_on_critical=data.get("block_on_critical", True),
        warn_on_high=data.get("warn_on_high", True),
    )


def default_policy() -> Policy:
    """Create default policy when none specified."""
    return Policy(
        rules=[
            PolicyRule(
                name="Executive Dashboards",
                pattern=r".*(exec|executive|dashboard).*",
                severity=Severity.CRITICAL,
                owners=["@data-platform"],
                require_approval=True,
            ),
            PolicyRule(
                name="ML Features",
                pattern=r".*(ml-feature|feature-store|model).*",
                severity=Severity.HIGH,
                owners=["@ml-engineering"],
                require_approval=True,
            ),
            PolicyRule(
                name="Compliance/Audit",
                pattern=r".*(compliance|audit|regulatory).*",
                severity=Severity.CRITICAL,
                owners=["@compliance"],
                require_approval=True,
            ),
        ]
    )


# =============================================================================
# Diff Parser
# =============================================================================

def parse_git_diff(base: str = "main", head: str = "HEAD") -> List[ChangedFile]:
    """Get changed files between two git refs."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-status", base, head],
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"git diff failed: {e.stderr}")
    except FileNotFoundError:
        raise RuntimeError("git not found in PATH")
    
    files = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        
        parts = line.split("\t")
        status = parts[0]
        
        if status.startswith("R"):  # Rename
            old_path, new_path = parts[1], parts[2]
            files.append(ChangedFile(
                path=new_path,
                change_type="renamed",
                old_path=old_path,
            ))
        else:
            path = parts[1]
            change_type = {
                "A": "added",
                "M": "modified",
                "D": "deleted",
            }.get(status, "modified")
            
            files.append(ChangedFile(path=path, change_type=change_type))
    
    return files


def parse_diff_file(path: str) -> List[ChangedFile]:
    """Parse a file containing list of changed files."""
    files = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            # Support format: "M path/to/file" or just "path/to/file"
            parts = line.split(maxsplit=1)
            if len(parts) == 2 and len(parts[0]) == 1:
                status, path = parts
                change_type = {"A": "added", "M": "modified", "D": "deleted"}.get(status, "modified")
            else:
                path = parts[0]
                change_type = "modified"
            
            files.append(ChangedFile(path=path, change_type=change_type))
    
    return files


def parse_github_pr(repo: str, pr_number: int, token: Optional[str] = None) -> List[ChangedFile]:
    """Fetch changed files from GitHub PR API."""
    if not HAS_REQUESTS:
        raise ImportError("requests required for GitHub integration. pip install requests")
    
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/files"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    
    files = []
    for file_data in resp.json():
        status = file_data["status"]
        change_type = {
            "added": "added",
            "removed": "deleted",
            "modified": "modified",
            "renamed": "renamed",
        }.get(status, "modified")
        
        files.append(ChangedFile(
            path=file_data["filename"],
            change_type=change_type,
            old_path=file_data.get("previous_filename"),
        ))
    
    return files


# =============================================================================
# Core Analysis Engine
# =============================================================================

class CheckEngine:
    """
    Main engine for running pre-merge checks.
    
    Combines:
    - Static analysis of changed files
    - OpenLineage runtime data
    - Policy evaluation
    """
    
    def __init__(
        self,
        policy: Optional[Policy] = None,
        openlineage_url: Optional[str] = None,
        openlineage_namespace: Optional[str] = None,
    ):
        self.policy = policy or default_policy()
        self.openlineage_url = openlineage_url
        self.openlineage_namespace = openlineage_namespace
        
        # Runtime lineage graph (populated from OpenLineage)
        self._runtime_graph: Dict[str, Set[str]] = {}  # asset -> downstream consumers
        self._runtime_jobs: Dict[str, Dict] = {}  # job_id -> metadata
        self._runtime_loaded = False
    
    def run(self, changed_files: List[ChangedFile]) -> CheckReport:
        """
        Run the full check pipeline.
        
        Args:
            changed_files: List of files changed in the PR
            
        Returns:
            CheckReport with results
        """
        # Step 1: Load OpenLineage data if configured
        if self.openlineage_url and not self._runtime_loaded:
            self._load_openlineage_data()
        
        # Step 2: Parse changed files for column/table changes
        column_changes = self._detect_column_changes(changed_files)
        
        # Step 3: Identify affected tables/assets from code
        code_assets = self._identify_affected_assets(changed_files)
        
        # Step 4: Expand blast radius using OpenLineage
        all_affected = self._expand_blast_radius(code_assets)
        
        # Step 5: Apply policy rules
        violations = self._evaluate_policy(all_affected)
        
        # Step 6: Determine result
        result = self._determine_result(violations)
        
        # Build report
        report = CheckReport(
            result=result,
            changed_files=changed_files,
            column_changes=column_changes,
            affected_assets=all_affected,
            violations=violations,
            total_downstream=len(all_affected),
            critical_count=len([a for a in all_affected if a.severity == Severity.CRITICAL]),
            high_count=len([a for a in all_affected if a.severity == Severity.HIGH]),
            openlineage_enriched=self._runtime_loaded,
        )
        
        return report
    
    def _load_openlineage_data(self):
        """Load lineage data from OpenLineage/Marquez."""
        if not HAS_REQUESTS:
            return
        
        try:
            # Fetch jobs
            url = f"{self.openlineage_url}/api/v1/namespaces"
            if self.openlineage_namespace:
                url = f"{self.openlineage_url}/api/v1/namespaces/{self.openlineage_namespace}/jobs"
            
            resp = requests.get(url, timeout=30)
            if not resp.ok:
                return
            
            data = resp.json()
            
            # Build dependency graph
            for job in data.get("jobs", []):
                job_id = f"job:{job.get('namespace', 'default')}/{job['name']}"
                self._runtime_jobs[job_id] = job
                
                # Track what this job reads/writes
                for output in job.get("outputs", []):
                    output_id = f"data:{output['namespace']}/{output['name']}"
                    
                    # Find downstream consumers
                    for other_job in data.get("jobs", []):
                        for inp in other_job.get("inputs", []):
                            if inp["namespace"] == output["namespace"] and inp["name"] == output["name"]:
                                other_id = f"job:{other_job.get('namespace', 'default')}/{other_job['name']}"
                                self._runtime_graph.setdefault(output_id, set()).add(other_id)
            
            self._runtime_loaded = True
            
        except Exception:
            # Graceful degradation - continue without OpenLineage
            pass
    
    def _detect_column_changes(self, files: List[ChangedFile]) -> List[ColumnChange]:
        """Detect column-level changes in PySpark/SQL files."""
        changes = []
        
        for f in files:
            if not f.path.endswith(".py"):
                continue
            
            # For now, flag deleted files as potential column removals
            if f.change_type == "deleted":
                changes.append(ColumnChange(
                    column="*",
                    table=None,
                    change_type="removed",
                ))
            
            # TODO: Full diff-based column detection
            # This would compare old vs new file AST
        
        return changes
    
    def _identify_affected_assets(self, files: List[ChangedFile]) -> List[AffectedAsset]:
        """Identify assets affected by file changes."""
        assets = []
        
        for f in files:
            # Map file to potential assets
            # This is a simplified heuristic - real implementation would parse the file
            
            if "etl" in f.path.lower() or "pipeline" in f.path.lower():
                # Likely a data pipeline job
                job_name = Path(f.path).stem
                assets.append(AffectedAsset(
                    id=f"job:{job_name}",
                    name=job_name,
                    asset_type="job",
                    severity=Severity.MEDIUM,
                    confidence=0.8,
                    path=[f.path],
                ))
            
            if "model" in f.path.lower() or "feature" in f.path.lower():
                # ML-related
                model_name = Path(f.path).stem
                assets.append(AffectedAsset(
                    id=f"ml:{model_name}",
                    name=model_name,
                    asset_type="ml-model",
                    severity=Severity.HIGH,
                    confidence=0.7,
                    path=[f.path],
                ))
        
        return assets
    
    def _expand_blast_radius(self, assets: List[AffectedAsset]) -> List[AffectedAsset]:
        """Expand affected assets using OpenLineage data."""
        all_assets = list(assets)
        seen = {a.id for a in assets}
        
        if not self._runtime_loaded:
            return all_assets
        
        # BFS to find downstream
        queue = [a.id for a in assets]
        
        while queue:
            current = queue.pop(0)
            
            # Find downstream consumers from runtime graph
            for downstream_id in self._runtime_graph.get(current, []):
                if downstream_id in seen:
                    continue
                seen.add(downstream_id)
                
                # Create affected asset
                name = downstream_id.split("/")[-1] if "/" in downstream_id else downstream_id
                all_assets.append(AffectedAsset(
                    id=downstream_id,
                    name=name,
                    asset_type="job" if downstream_id.startswith("job:") else "table",
                    severity=Severity.MEDIUM,
                    confidence=1.0,  # From OpenLineage = observed
                    path=[current, downstream_id],
                ))
                
                queue.append(downstream_id)
        
        return all_assets
    
    def _evaluate_policy(self, assets: List[AffectedAsset]) -> List[PolicyViolation]:
        """Evaluate policy rules against affected assets."""
        import re
        violations = []
        
        for rule in self.policy.rules:
            pattern = re.compile(rule.pattern, re.IGNORECASE)
            
            matching_assets = [
                a for a in assets
                if pattern.search(a.id) or pattern.search(a.name)
            ]
            
            if matching_assets:
                # Update severity on matching assets
                for a in matching_assets:
                    a.severity = rule.severity
                    a.owners = rule.owners
                
                if rule.require_approval:
                    violations.append(PolicyViolation(
                        rule_name=rule.name,
                        severity=rule.severity,
                        message=f"Changes affect {len(matching_assets)} {rule.name.lower()} assets",
                        affected_assets=[a.id for a in matching_assets],
                        required_approvers=rule.owners,
                    ))
        
        return violations
    
    def _determine_result(self, violations: List[PolicyViolation]) -> CheckResult:
        """Determine final check result."""
        if any(v.severity == Severity.CRITICAL for v in violations):
            if self.policy.block_on_critical:
                return CheckResult.BLOCKED
        
        if any(v.severity == Severity.HIGH for v in violations):
            if self.policy.warn_on_high:
                return CheckResult.WARN
        
        if violations:
            return CheckResult.WARN
        
        return CheckResult.PASS


# =============================================================================
# CLI Command
# =============================================================================

@click.command()
@click.option("--diff", "diff_file", type=click.Path(exists=True),
              help="File containing list of changed files")
@click.option("--git-diff", "git_diff", nargs=2, metavar="BASE HEAD",
              help="Git refs to diff (e.g., main HEAD)")
@click.option("--github-pr", type=int, help="GitHub PR number")
@click.option("--repo", help="GitHub repo (owner/repo) for --github-pr")
@click.option("--openlineage-url", envvar="OPENLINEAGE_URL",
              help="OpenLineage/Marquez API URL")
@click.option("--openlineage-namespace", envvar="OPENLINEAGE_NAMESPACE",
              help="OpenLineage namespace to query")
@click.option("--policy", "policy_file", type=click.Path(exists=True),
              help="Policy YAML file")
@click.option("--fail-if-critical", is_flag=True,
              help="Exit 1 if critical systems affected")
@click.option("--output", "-o", type=click.Path(),
              help="Write JSON report to file")
@click.option("--format", "output_format", type=click.Choice(["text", "json", "markdown"]),
              default="text", help="Output format")
@click.option("--quiet", "-q", is_flag=True,
              help="Minimal output (just exit code)")
def check(
    diff_file: Optional[str],
    git_diff: Optional[Tuple[str, str]],
    github_pr: Optional[int],
    repo: Optional[str],
    openlineage_url: Optional[str],
    openlineage_namespace: Optional[str],
    policy_file: Optional[str],
    fail_if_critical: bool,
    output: Optional[str],
    output_format: str,
    quiet: bool,
):
    """
    Run pre-merge impact analysis for CI/CD gates.
    
    Analyzes changed files, enriches with OpenLineage data,
    and evaluates against policy rules.
    
    \b
    Examples:
        # From git diff
        jnkn check --git-diff main HEAD
        
        # From file list
        jnkn check --diff changed_files.txt
        
        # With OpenLineage
        jnkn check --git-diff main HEAD --openlineage-url http://marquez:5000
        
        # With policy
        jnkn check --git-diff main HEAD --policy policy.yaml --fail-if-critical
        
        # GitHub Actions
        jnkn check --github-pr 123 --repo owner/repo
    
    \b
    Exit Codes:
        0 - Safe to merge
        1 - Blocked (critical impact)
        2 - Warning (review required)
    """
    # Get changed files
    try:
        if diff_file:
            changed_files = parse_diff_file(diff_file)
        elif git_diff:
            changed_files = parse_git_diff(git_diff[0], git_diff[1])
        elif github_pr:
            if not repo:
                raise click.UsageError("--repo required with --github-pr")
            token = os.environ.get("GITHUB_TOKEN")
            changed_files = parse_github_pr(repo, github_pr, token)
        else:
            # Default: diff against main
            changed_files = parse_git_diff("main", "HEAD")
    except Exception as e:
        click.echo(click.style(f"Error getting changed files: {e}", fg="red"), err=True)
        sys.exit(1)
    
    if not changed_files:
        if not quiet:
            click.echo(click.style("No changed files detected", fg="yellow"))
        sys.exit(0)
    
    # Load policy
    policy = None
    if policy_file:
        try:
            policy = load_policy(policy_file)
        except Exception as e:
            click.echo(click.style(f"Error loading policy: {e}", fg="red"), err=True)
            sys.exit(1)
    
    # Run check
    engine = CheckEngine(
        policy=policy,
        openlineage_url=openlineage_url,
        openlineage_namespace=openlineage_namespace,
    )
    
    report = engine.run(changed_files)
    
    # Override result if --fail-if-critical
    if fail_if_critical and report.critical_count > 0:
        report.result = CheckResult.BLOCKED
    
    # Output
    if output:
        with open(output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
    
    if not quiet:
        if output_format == "json":
            click.echo(json.dumps(report.to_dict(), indent=2))
        elif output_format == "markdown":
            click.echo(report.to_markdown())
        else:
            _print_report(report)
    
    # Exit with appropriate code
    sys.exit(report.result.value)


def _print_report(report: CheckReport):
    """Print formatted report to terminal."""
    click.echo()
    
    # Result banner
    if report.result == CheckResult.BLOCKED:
        click.echo(click.style("╔════════════════════════════════════════╗", fg="red"))
        click.echo(click.style("║  ❌ BLOCKED - Critical Impact Detected ║", fg="red", bold=True))
        click.echo(click.style("╚════════════════════════════════════════╝", fg="red"))
    elif report.result == CheckResult.WARN:
        click.echo(click.style("╔═══════════════════════════════════════╗", fg="yellow"))
        click.echo(click.style("║  ⚠️  WARNING - Review Required         ║", fg="yellow", bold=True))
        click.echo(click.style("╚═══════════════════════════════════════╝", fg="yellow"))
    else:
        click.echo(click.style("╔════════════════════════════════════════╗", fg="green"))
        click.echo(click.style("║  ✅ PASSED - Safe to Merge             ║", fg="green", bold=True))
        click.echo(click.style("╚════════════════════════════════════════╝", fg="green"))
    
    click.echo()
    
    # Summary
    click.echo(click.style("Summary:", bold=True))
    click.echo(f"  Changed files:     {len(report.changed_files)}")
    click.echo(f"  Column changes:    {len(report.column_changes)}")
    click.echo(f"  Downstream impact: {report.total_downstream}")
    click.echo(f"  Critical systems:  {report.critical_count}")
    click.echo(f"  High severity:     {report.high_count}")
    
    if report.openlineage_enriched:
        click.echo(click.style("  📊 Enriched with OpenLineage", fg="cyan"))
    
    # Violations
    if report.violations:
        click.echo()
        click.echo(click.style("Policy Violations:", bold=True, fg="red"))
        for v in report.violations:
            icon = "🚨" if v.severity == Severity.CRITICAL else "⚠️"
            click.echo(f"  {icon} {v.rule_name}: {v.message}")
            if v.required_approvers:
                approvers = ", ".join(v.required_approvers)
                click.echo(click.style(f"     Required approvers: {approvers}", dim=True))
    
    # Critical assets
    critical = [a for a in report.affected_assets if a.severity == Severity.CRITICAL]
    if critical:
        click.echo()
        click.echo(click.style("Critical Systems Affected:", bold=True, fg="red"))
        for a in critical:
            owners = f" (owners: {', '.join(a.owners)})" if a.owners else ""
            click.echo(f"  • {a.name}{owners}")
    
    # Changed files
    if report.changed_files:
        click.echo()
        click.echo(click.style("Changed Files:", bold=True))
        for f in report.changed_files[:10]:
            icon = {"added": "+", "deleted": "-", "modified": "~", "renamed": "→"}.get(f.change_type, "?")
            click.echo(f"  {icon} {f.path}")
        if len(report.changed_files) > 10:
            click.echo(f"  ... and {len(report.changed_files) - 10} more")
    
    click.echo()


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    check()