"""
Check Command - CI/CD Gate for Pre-Merge Impact Analysis.
Standardized output version.
"""

import sys
from dataclasses import dataclass
from enum import Enum
from typing import List, Tuple

import click
from pydantic import BaseModel, Field

from ..renderers import JsonRenderer


# --- API Models ---
class CheckResultStatus(str, Enum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"
    WARN = "WARN"


class ApiChangedFile(BaseModel):
    path: str
    change_type: str


class ApiViolation(BaseModel):
    rule: str
    severity: str
    message: str


class CheckResponse(BaseModel):
    """
    Standardized response for check command.
    Maps internal CheckReport to external API contract.
    """

    result: CheckResultStatus
    exit_code: int
    changed_files_count: int
    critical_count: int
    high_count: int
    violations: List[ApiViolation] = Field(default_factory=list)
    details_url: str | None = None  # For future dashboard links


# --- Internal Classes (Normally imported from check logic module) ---
class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CheckResult(Enum):
    PASS = 0
    BLOCKED = 1
    WARN = 2


@dataclass
class ChangedFile:
    path: str
    change_type: str
    old_path: str | None = None


class _null_context:
    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


# =============================================================================
# CLI Command
# =============================================================================


@click.command()
@click.option("--diff", "diff_file", type=click.Path(exists=True))
@click.option("--git-diff", "git_diff", nargs=2)
@click.option("--fail-if-critical", is_flag=True)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON (Standard Envelope)")
@click.option("--format", "output_format", type=click.Choice(["text", "markdown"]), default="text")
@click.option("--quiet", "-q", is_flag=True)
def check(
    diff_file: str | None,
    git_diff: Tuple[str, str] | None,
    fail_if_critical: bool,
    as_json: bool,
    output_format: str,
    quiet: bool,
):
    """Run pre-merge impact analysis."""
    renderer = JsonRenderer("check")

    # Context handling
    context_manager = renderer.capture() if as_json else _null_context()

    error_to_report = None
    api_response = None

    with context_manager:
        try:
            # 1. Get changed files
            changed_files = []
            if diff_file:
                # Mock implementation for snippet
                changed_files = [ChangedFile("file.py", "modified")]
            elif git_diff:
                # Mock implementation
                changed_files = [ChangedFile("app.py", "modified")]
            else:
                # Default behavior
                changed_files = []

            # 2. Run Engine (Mocked logic for migration demonstration)
            # In real file, instantiate CheckEngine and run()
            # report = engine.run(changed_files)

            # Mock Report for demonstration
            @dataclass
            class MockReport:
                result = CheckResult.PASS
                changed_files = changed_files
                critical_count = 0
                high_count = 0
                violations = []

            report = MockReport()
            report.changed_files = changed_files  # Ensure it matches scope

            if fail_if_critical and report.critical_count > 0:
                report.result = CheckResult.BLOCKED

            # 3. Map to API Model
            api_response = CheckResponse(
                result=CheckResultStatus[report.result.name],
                exit_code=report.result.value,
                changed_files_count=len(report.changed_files),
                critical_count=report.critical_count,
                high_count=report.high_count,
                violations=[],
            )

        except Exception as e:
            error_to_report = e

    # Render
    if as_json:
        if error_to_report:
            renderer.render_error(error_to_report)
            sys.exit(1)
        elif api_response:
            renderer.render_success(api_response)
            sys.exit(api_response.exit_code)
    else:
        # Legacy Text Output
        if not quiet and api_response:
            click.echo(f"Result: {api_response.result.value}")
        if api_response:
            sys.exit(api_response.exit_code)
        sys.exit(1)
