#!/usr/bin/env python3
"""
End-to-End Demo: CI/CD Gate for Pre-Merge Impact Analysis

This demo simulates the complete flow of:
1. A PR is opened with changes to a PySpark ETL job
2. Jnkn analyzes the changed files
3. OpenLineage data enriches the blast radius
4. Policy rules are evaluated
5. The PR is blocked/warned/passed

Run this demo:
    python demo_cicd_gate.py
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from jnkn.cli.commands.check import (
    CheckEngine,
    CheckResult,
    ChangedFile,
    Policy,
    PolicyRule,
    Severity,
    AffectedAsset,
)


# =============================================================================
# Mock Data
# =============================================================================

def create_mock_openlineage_data():
    """
    Simulate OpenLineage data that would come from Marquez.
    
    This represents the actual production lineage:
    - daily_user_etl writes to dim_users
    - user_metrics_aggregator reads dim_users, writes agg_user_metrics
    - executive_dashboard_loader reads agg_user_metrics, writes exec_dashboard
    - churn_prediction_features reads dim_users, writes ml-features/churn
    """
    return {
        # What each job reads/writes
        "jobs": [
            {
                "name": "daily_user_etl",
                "namespace": "spark",
                "inputs": [
                    {"namespace": "postgres", "name": "public.raw_users"},
                    {"namespace": "postgres", "name": "public.user_events"},
                ],
                "outputs": [
                    {"namespace": "s3", "name": "warehouse/dim_users"},
                ],
            },
            {
                "name": "user_metrics_aggregator",
                "namespace": "spark",
                "inputs": [
                    {"namespace": "s3", "name": "warehouse/dim_users"},
                ],
                "outputs": [
                    {"namespace": "s3", "name": "warehouse/agg_user_metrics"},
                ],
            },
            {
                "name": "executive_dashboard_loader",
                "namespace": "spark",
                "inputs": [
                    {"namespace": "s3", "name": "warehouse/agg_user_metrics"},
                ],
                "outputs": [
                    {"namespace": "redshift", "name": "analytics.exec_dashboard"},
                ],
            },
            {
                "name": "churn_prediction_features",
                "namespace": "spark",
                "inputs": [
                    {"namespace": "s3", "name": "warehouse/dim_users"},
                ],
                "outputs": [
                    {"namespace": "s3", "name": "ml-features/churn_features"},
                ],
            },
            {
                "name": "marketing_campaign_loader",
                "namespace": "spark",
                "inputs": [
                    {"namespace": "s3", "name": "warehouse/dim_users"},
                ],
                "outputs": [
                    {"namespace": "redshift", "name": "marketing.campaign_targets"},
                ],
            },
        ],
    }


def create_mock_policy():
    """Create policy rules for the demo."""
    return Policy(
        rules=[
            PolicyRule(
                name="Executive Dashboards",
                pattern=r".*(exec|executive).*dashboard.*",
                severity=Severity.CRITICAL,
                owners=["@data-platform-team", "@analytics-leadership"],
                require_approval=True,
            ),
            PolicyRule(
                name="ML Feature Pipelines",
                pattern=r".*(ml-feature|churn|model).*",
                severity=Severity.HIGH,
                owners=["@ml-engineering"],
                require_approval=True,
            ),
            PolicyRule(
                name="Marketing Systems",
                pattern=r".*marketing.*",
                severity=Severity.MEDIUM,
                owners=["@marketing-analytics"],
                require_approval=False,
            ),
        ],
        block_on_critical=True,
        warn_on_high=True,
    )


class MockCheckEngine(CheckEngine):
    """
    CheckEngine with mocked OpenLineage data for demo purposes.
    """
    
    def __init__(self, policy: Policy, openlineage_data: dict):
        super().__init__(policy=policy)
        self._mock_ol_data = openlineage_data
        self._build_runtime_graph()
    
    def _build_runtime_graph(self):
        """Build the runtime dependency graph from mock data."""
        # Map outputs to downstream consumers
        output_to_consumers = {}
        
        for job in self._mock_ol_data["jobs"]:
            job_id = f"job:spark/{job['name']}"
            self._runtime_jobs[job_id] = job
            
            # Track what this job produces
            for output in job.get("outputs", []):
                output_id = f"data:{output['namespace']}/{output['name']}"
                output_to_consumers.setdefault(output_id, set())
        
        # Find consumers for each output
        for job in self._mock_ol_data["jobs"]:
            job_id = f"job:spark/{job['name']}"
            
            for inp in job.get("inputs", []):
                input_id = f"data:{inp['namespace']}/{inp['name']}"
                
                # This job consumes this input
                if input_id in output_to_consumers:
                    output_to_consumers[input_id].add(job_id)
                    
                    # Also add this job's outputs as downstream
                    for output in job.get("outputs", []):
                        output_id = f"data:{output['namespace']}/{output['name']}"
                        output_to_consumers.setdefault(input_id, set()).add(output_id)
        
        self._runtime_graph = output_to_consumers
        self._runtime_loaded = True
    
    def _identify_affected_assets(self, files: List[ChangedFile]) -> List[AffectedAsset]:
        """Identify assets from changed files - enhanced for demo."""
        assets = []
        
        for f in files:
            # Match file to job by name
            file_stem = Path(f.path).stem
            
            for job in self._mock_ol_data["jobs"]:
                if file_stem.lower() in job["name"].lower() or job["name"].lower() in file_stem.lower():
                    job_id = f"job:spark/{job['name']}"
                    
                    assets.append(AffectedAsset(
                        id=job_id,
                        name=job["name"],
                        asset_type="job",
                        severity=Severity.MEDIUM,
                        confidence=0.95,
                        path=[f.path, job_id],
                    ))
                    
                    # Add outputs as directly affected
                    for output in job.get("outputs", []):
                        output_id = f"data:{output['namespace']}/{output['name']}"
                        assets.append(AffectedAsset(
                            id=output_id,
                            name=output["name"],
                            asset_type="table",
                            severity=Severity.MEDIUM,
                            confidence=0.95,
                            path=[f.path, job_id, output_id],
                        ))
        
        return assets


# =============================================================================
# Demo Scenarios
# =============================================================================

def demo_scenario_1():
    """
    Scenario 1: Modify the daily_user_etl job
    
    This should:
    - Detect impact on dim_users
    - Find downstream: user_metrics_aggregator, exec_dashboard, churn_features
    - BLOCK due to executive dashboard impact
    """
    print("=" * 70)
    print("SCENARIO 1: Modify daily_user_etl.py")
    print("=" * 70)
    print("""
    Simulating PR #1234:
    - Changed file: src/jobs/daily_user_etl.py
    - Change: Modified event_count calculation
    """)
    
    changed_files = [
        ChangedFile(path="src/jobs/daily_user_etl.py", change_type="modified"),
    ]
    
    engine = MockCheckEngine(
        policy=create_mock_policy(),
        openlineage_data=create_mock_openlineage_data(),
    )
    
    report = engine.run(changed_files)
    
    _print_demo_report(report)
    
    return report


def demo_scenario_2():
    """
    Scenario 2: Modify a marketing job (medium severity)
    
    This should:
    - Detect impact on campaign_targets
    - WARN but not block
    """
    print("\n" + "=" * 70)
    print("SCENARIO 2: Modify marketing_campaign_loader.py")
    print("=" * 70)
    print("""
    Simulating PR #1235:
    - Changed file: src/jobs/marketing_campaign_loader.py
    - Change: Added new filter criteria
    """)
    
    changed_files = [
        ChangedFile(path="src/jobs/marketing_campaign_loader.py", change_type="modified"),
    ]
    
    engine = MockCheckEngine(
        policy=create_mock_policy(),
        openlineage_data=create_mock_openlineage_data(),
    )
    
    report = engine.run(changed_files)
    
    _print_demo_report(report)
    
    return report


def demo_scenario_3():
    """
    Scenario 3: Add a new file (safe change)
    
    This should:
    - Detect no downstream impact
    - PASS
    """
    print("\n" + "=" * 70)
    print("SCENARIO 3: Add new_utility_script.py")
    print("=" * 70)
    print("""
    Simulating PR #1236:
    - Added file: src/utils/new_utility_script.py
    - Change: New helper function
    """)
    
    changed_files = [
        ChangedFile(path="src/utils/new_utility_script.py", change_type="added"),
    ]
    
    engine = MockCheckEngine(
        policy=create_mock_policy(),
        openlineage_data=create_mock_openlineage_data(),
    )
    
    report = engine.run(changed_files)
    
    _print_demo_report(report)
    
    return report


def demo_scenario_4():
    """
    Scenario 4: Delete an ETL job (dangerous!)
    
    This should:
    - Detect the job is being removed
    - Find all downstream dependencies
    - BLOCK
    """
    print("\n" + "=" * 70)
    print("SCENARIO 4: DELETE daily_user_etl.py")
    print("=" * 70)
    print("""
    Simulating PR #1237:
    - DELETED file: src/jobs/daily_user_etl.py
    - Change: Removing the entire job
    """)
    
    changed_files = [
        ChangedFile(path="src/jobs/daily_user_etl.py", change_type="deleted"),
    ]
    
    engine = MockCheckEngine(
        policy=create_mock_policy(),
        openlineage_data=create_mock_openlineage_data(),
    )
    
    report = engine.run(changed_files)
    
    _print_demo_report(report)
    
    return report


def _print_demo_report(report):
    """Print a formatted report for the demo."""
    print()
    
    # Result banner
    if report.result == CheckResult.BLOCKED:
        print("\033[91m" + "╔════════════════════════════════════════╗")
        print("║  ❌ BLOCKED - Critical Impact Detected ║")
        print("╚════════════════════════════════════════╝" + "\033[0m")
    elif report.result == CheckResult.WARN:
        print("\033[93m" + "╔═══════════════════════════════════════╗")
        print("║  ⚠️  WARNING - Review Required         ║")
        print("╚═══════════════════════════════════════╝" + "\033[0m")
    else:
        print("\033[92m" + "╔════════════════════════════════════════╗")
        print("║  ✅ PASSED - Safe to Merge             ║")
        print("╚════════════════════════════════════════╝" + "\033[0m")
    
    print()
    print("Summary:")
    print(f"  Exit code:         {report.result.value}")
    print(f"  Changed files:     {len(report.changed_files)}")
    print(f"  Downstream impact: {report.total_downstream}")
    print(f"  Critical systems:  {report.critical_count}")
    print(f"  High severity:     {report.high_count}")
    print(f"  OpenLineage:       {'✓ Enriched' if report.openlineage_enriched else '✗ Not available'}")
    
    # Violations
    if report.violations:
        print()
        print("\033[91mPolicy Violations:\033[0m")
        for v in report.violations:
            icon = "🚨" if v.severity == Severity.CRITICAL else "⚠️"
            print(f"  {icon} {v.rule_name}: {v.message}")
            if v.required_approvers:
                print(f"     Required: {', '.join(v.required_approvers)}")
    
    # Affected assets
    if report.affected_assets:
        print()
        print("Affected Assets:")
        
        # Group by severity
        critical = [a for a in report.affected_assets if a.severity == Severity.CRITICAL]
        high = [a for a in report.affected_assets if a.severity == Severity.HIGH]
        other = [a for a in report.affected_assets if a.severity not in (Severity.CRITICAL, Severity.HIGH)]
        
        if critical:
            print("  \033[91mCRITICAL:\033[0m")
            for a in critical:
                print(f"    • {a.name} ({a.asset_type})")
        
        if high:
            print("  \033[93mHIGH:\033[0m")
            for a in high:
                print(f"    • {a.name} ({a.asset_type})")
        
        if other and len(other) <= 5:
            print("  OTHER:")
            for a in other:
                print(f"    • {a.name} ({a.asset_type})")
        elif other:
            print(f"  OTHER: {len(other)} more assets")


# =============================================================================
# GitHub Actions Output Format
# =============================================================================

def demo_github_actions_output():
    """Show what the GitHub Actions integration would output."""
    print("\n" + "=" * 70)
    print("GITHUB ACTIONS PR COMMENT PREVIEW")
    print("=" * 70)
    
    # Run scenario 1
    changed_files = [
        ChangedFile(path="src/jobs/daily_user_etl.py", change_type="modified"),
    ]
    
    engine = MockCheckEngine(
        policy=create_mock_policy(),
        openlineage_data=create_mock_openlineage_data(),
    )
    
    report = engine.run(changed_files)
    
    # Print markdown output
    print("\n--- PR Comment (Markdown) ---\n")
    print(report.to_markdown())
    
    print("\n--- JSON Output (for artifacts) ---\n")
    print(json.dumps(report.to_dict(), indent=2))


# =============================================================================
# Integration Example
# =============================================================================

def show_cli_usage():
    """Show how to use this in real CI/CD."""
    print("\n" + "=" * 70)
    print("CLI USAGE EXAMPLES")
    print("=" * 70)
    
    print("""
    # Basic usage (git diff against main)
    jnkn check --git-diff main HEAD
    
    # With OpenLineage enrichment
    jnkn check --git-diff main HEAD \\
        --openlineage-url http://marquez.internal:5000 \\
        --openlineage-namespace spark-production
    
    # With policy enforcement
    jnkn check --git-diff main HEAD \\
        --policy policy.yaml \\
        --fail-if-critical
    
    # GitHub Actions (uses GITHUB_TOKEN automatically)
    jnkn check --github-pr ${{ github.event.pull_request.number }} \\
        --repo ${{ github.repository }} \\
        --output impact-report.json \\
        --format markdown
    
    # From a file containing changed paths
    git diff --name-only main HEAD > changed_files.txt
    jnkn check --diff changed_files.txt
    """)


def show_github_actions_workflow():
    """Show the GitHub Actions workflow YAML."""
    print("\n" + "=" * 70)
    print("GITHUB ACTIONS WORKFLOW")
    print("=" * 70)
    
    workflow = '''
name: Jnkn Impact Analysis

on:
  pull_request:
    paths:
      - 'src/**/*.py'
      - 'dbt/**/*.sql'
      - 'terraform/**/*.tf'

jobs:
  impact-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need full history for diff
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Jnkn
        run: pip install jnkn
      
      - name: Run Impact Analysis
        id: check
        env:
          OPENLINEAGE_URL: ${{ secrets.MARQUEZ_URL }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          jnkn check \\
            --git-diff origin/${{ github.base_ref }} HEAD \\
            --openlineage-url $OPENLINEAGE_URL \\
            --policy policy.yaml \\
            --output impact-report.json \\
            --format json
        continue-on-error: true
      
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('impact-report.json', 'utf8'));
            
            let body = '## 🔍 Jnkn Impact Analysis\\n\\n';
            
            if (report.result === 'BLOCKED') {
              body += '### ❌ BLOCKED\\n\\n';
              body += `**${report.summary.critical_count}** critical systems affected.\\n`;
              body += 'This PR requires approval before merging.\\n\\n';
            } else if (report.result === 'WARN') {
              body += '### ⚠️ Warning\\n\\n';
            } else {
              body += '### ✅ Passed\\n\\n';
            }
            
            body += `| Metric | Count |\\n|--------|-------|\\n`;
            body += `| Downstream Impact | ${report.summary.total_downstream} |\\n`;
            body += `| Critical Systems | ${report.summary.critical_count} |\\n`;
            
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: body
            });
      
      - name: Enforce Gate
        if: steps.check.outcome == 'failure'
        run: |
          echo "::error::Jnkn detected critical impact. PR blocked."
          exit 1
'''
    print(workflow)


# =============================================================================
# Main
# =============================================================================

def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║   JUNKAN CI/CD GATE DEMO                                          ║
    ║   Pre-Merge Impact Analysis                                       ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    
    This demo shows how Jnkn integrates with CI/CD pipelines to
    prevent breaking changes from reaching production.
    
    The flow:
    1. PR is opened
    2. Jnkn analyzes changed files
    3. OpenLineage data enriches blast radius
    4. Policy rules are evaluated
    5. PR is BLOCKED / WARNED / PASSED
    """)
    
    # Run all scenarios
    demo_scenario_1()  # Modify ETL job - BLOCKED
    demo_scenario_2()  # Modify marketing job - WARN
    demo_scenario_3()  # Add new file - PASS
    demo_scenario_4()  # Delete ETL job - BLOCKED
    
    # Show GitHub Actions output
    demo_github_actions_output()
    
    # Show usage
    show_cli_usage()
    show_github_actions_workflow()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("""
    Key Takeaways:
    
    1. BLOCKED (exit 1): Critical systems like executive dashboards
       are affected. PR cannot merge without explicit approval.
    
    2. WARN (exit 2): High-severity systems like ML pipelines are
       affected. PR can merge but stakeholders are notified.
    
    3. PASS (exit 0): No policy violations. Safe to merge.
    
    The power comes from combining:
    - Static analysis (what the code change does)
    - OpenLineage data (what actually depends on it in production)
    - Policy rules (what's critical to the business)
    
    Without OpenLineage, we'd only know "this file changed".
    With OpenLineage, we know "this change affects the CEO dashboard".
    """)


if __name__ == "__main__":
    main()