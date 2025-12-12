"""
Explain Command - Show why matches were made.

Wraps the ExplanationGenerator for CLI access.
"""

import click


@click.command()
@click.argument("source_id")
@click.argument("target_id")
@click.option("--min-confidence", default=0.5, type=float, help="Minimum confidence threshold")
@click.option("--why-not", is_flag=True, help="Explain why match was NOT made")
@click.option("--alternatives", is_flag=True, help="Show alternative matches that were considered")
def explain(
    source_id: str, target_id: str, min_confidence: float, why_not: bool, alternatives: bool
):
    """
    Explain why a match was made (or not made).

    Shows the confidence calculation, signals considered, and
    alternative matches that were rejected.

    \b
    Examples:
        jnkn explain env:PAYMENT_DB_HOST infra:payment_db_host
        jnkn explain env:HOST infra:main --why-not
        jnkn explain env:DB_URL infra:database --alternatives
    """
    try:
        from ...analysis.explain import create_explanation_generator

        generator = create_explanation_generator(min_confidence=min_confidence)

        if why_not:
            output = generator.explain_why_not(source_id, target_id)
        else:
            explanation = generator.explain(source_id, target_id, find_alternatives=alternatives)
            output = generator.format(explanation)

        click.echo(output)

    except ImportError:
        # Fallback: basic explanation
        click.echo("=" * 60)
        click.echo("MATCH EXPLANATION")
        click.echo("=" * 60)
        click.echo()
        click.echo(f"Source: {source_id}")
        click.echo(f"Target: {target_id}")
        click.echo()
        click.echo("⚠️  Full explanation requires analysis module.")
        click.echo("   Install with: pip install jnkn[full]")
