"""
jnkn CLI - Main entry point.

This module registers all CLI commands. Each command is implemented
in its own module under cli/commands/.
"""

import click

from .commands import scan, impact, trace, graph, lint, ingest, init
from .commands import blast_radius, check, diff, explain, suppress, stats


@click.group()
@click.version_option(package_name="jnkn")
def main():
    """jnkn: Pre-Flight Impact Analysis Engine.
    
    Detects cross-domain breaking changes between Infrastructure,
    Data Pipelines, and Application Code.
    
    \b
    Quick Start:
      jnkn scan ./src --output lineage.json
      jnkn impact warehouse.dim_users
      jnkn graph --output lineage.html
    
    \b
    Documentation:
      https://github.com/your-org/jnkn
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
main.add_command(init)

if __name__ == "__main__":
    main()