"""
jnkn CLI - Main entry point.

This module registers all CLI commands.
"Zone B" commands are registered but hidden to keep the user experience
focused for the 0.0.1 launch, while still allowing integration tests
and power users to access them.
"""

import click

from .commands import (
    action,
    blast_radius,
    check,
    diff,
    explain,
    feedback,
    graph,
    impact,
    ingest,
    lint,
    review,
    scan,
    stats,
    suppress,
    trace,
    visualize,
    watch,
)
from .commands.initialize import init
from .utils_telemetry import TelemetryGroup


# Use cls=TelemetryGroup to enable automatic tracking
@click.group(cls=TelemetryGroup)
@click.version_option(package_name="jnkn")
def main():
    """jnkn: The Pre-Flight Impact Analysis Engine.

    Detects cross-domain breaking changes between Infrastructure,
    Data Pipelines, and Application Code.
    """
    pass


# =============================================================================
# ZONE A: Public Interface (Launch Critical)
# These are the only commands visible in `jnkn --help`
# =============================================================================

main.add_command(init)
main.add_command(check.check)
main.add_command(watch.watch)
main.add_command(feedback.feedback)


# =============================================================================
# ZONE B: Hidden / Advanced (Fully Functional)
# These commands work (and are tested) but are hidden from the CLI help
# to reduce cognitive load during onboarding.
# =============================================================================

# 1. Core Logic (Used by check/tests)
scan.scan.hidden = True
main.add_command(scan.scan)

blast_radius.blast_radius.hidden = True
main.add_command(blast_radius.blast_radius, name="blast")

# 2. CI/CD Internals
action.action.hidden = True
main.add_command(action.action)

# 3. Debugging & Visualization
graph.graph.hidden = True
main.add_command(graph.graph)

visualize.visualize.hidden = True
main.add_command(visualize.visualize)

trace.trace.hidden = True
main.add_command(trace.trace)

impact.impact.hidden = True
main.add_command(impact.impact)

explain.explain.hidden = True
main.add_command(explain.explain)

# 4. Maintenance & Tuning
stats.stats.hidden = True
main.add_command(stats.stats)

stats.clear.hidden = True
main.add_command(stats.clear)

suppress.suppress.hidden = True
main.add_command(suppress.suppress)

review.review.hidden = True
main.add_command(review.review)

lint.lint.hidden = True
main.add_command(lint.lint)

diff.diff.hidden = True
main.add_command(diff.diff)

ingest.ingest.hidden = True
main.add_command(ingest.ingest)


if __name__ == "__main__":
    main()