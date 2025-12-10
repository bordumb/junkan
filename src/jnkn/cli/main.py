"""
jnkn CLI - Main entry point.

This module registers all CLI commands. Each command is implemented
in its own module under cli/commands/.
"""

import click

from .commands import (
    blast_radius,
    check,
    diff,
    explain,
    feedback,
    graph,
    impact,
    ingest,
    lint,
    scan,
    stats,
    suppress,
    trace,
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


# Register commands
main.add_command(scan.scan)
main.add_command(impact.impact)
main.add_command(trace.trace)
main.add_command(graph.graph)
main.add_command(lint.lint)
main.add_command(ingest.ingest)
main.add_command(blast_radius.blast_radius, name="blast")
main.add_command(explain.explain)
main.add_command(suppress.suppress)
main.add_command(stats.stats)
main.add_command(stats.clear)
main.add_command(check.check)
main.add_command(diff.diff)
main.add_command(feedback.feedback)
main.add_command(init)

if __name__ == "__main__":
    main()
