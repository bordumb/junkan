"""
Review Command - Interactive triage of dependency matches.

This command provides a Terminal User Interface (TUI) for rapidly reviewing,
confirming, or suppressing dependency edges found by the scan. It interacts
directly with the SuppressionStore to persist decisions immediately.
"""

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from ...analysis.explain import create_explanation_generator
from ...core.mode import get_mode_manager
from ...stitching.patterns import suggest_patterns
from ...stitching.suppressions import SuppressionStore
from ..utils import load_graph

console = Console()


@click.command()
@click.option("--min-confidence", default=0.0, help="Review matches above this score")
@click.option("--max-confidence", default=0.8, help="Review matches below this score")
@click.option("-g", "--graph", "graph_file", default=".jnkn/jnkn.db", help="Path to graph database")
def review(min_confidence: float, max_confidence: float, graph_file: str):
    """
    Interactively review and suppress matches.

    Iterates through edges within the specified confidence range.
    Allows users to:
    - [y] Confirm: Mark as reviewed (currently a no-op/skip)
    - [n] Suppress: Create a suppression rule (Exact or Pattern)
    - [e] Explain: Show detailed confidence scoring logic
    - [s] Skip: Move to next item
    - [q] Quit: Exit the review session
    """
    # 1. Load Data
    graph = load_graph(graph_file)
    if not graph:
        return

    suppression_store = SuppressionStore()
    suppression_store.load()

    # 2. Filter Edges to Review
    # We prioritize low/medium confidence edges that are likely to be false positives
    # Filter out edges that are ALREADY suppressed
    edges_to_review = []
    for edge in graph.iter_edges():
        if not (min_confidence <= edge.confidence <= max_confidence):
            continue

        # Check if already suppressed
        if suppression_store.is_suppressed(edge.source_id, edge.target_id).suppressed:
            continue

        edges_to_review.append(edge)

    if not edges_to_review:
        console.print("[green]No matches found needing review in that confidence range.[/green]")
        return

    console.print(
        f"🔍 Found [bold]{len(edges_to_review)}[/bold] potential matches. Verify valid links or suppress false positives.\n"
    )

    explainer = create_explanation_generator(graph)

    # 3. Interactive Loop
    # We iterate by index to handle dynamic list filtering if needed in future
    i = 0
    # Track how many items we process in this session
    processed_count = 0

    while i < len(edges_to_review):
        edge = edges_to_review[i]

        # Re-check suppression (Critical for Auto-Prune)
        # If a user adds a wildcard suppression in step i, it might cover step i+5.
        if suppression_store.is_suppressed(edge.source_id, edge.target_id).suppressed:
            i += 1
            continue

        # Display Edge
        _print_edge_panel(edge, i + 1, len(edges_to_review))

        # Print the menu BEFORE asking for input so the user knows what to do
        console.print("[dim][Y] Confirm   [N] Suppress   [S] Skip   [E] Explain   [Q] Quit[/dim]")

        # More descriptive prompt text
        choice = Prompt.ask(
            "Select action",
            choices=["y", "n", "s", "e", "q"],
            default="y",
            show_choices=False,
            show_default=False,
        )

        if choice == "q":
            break

        elif choice == "y":
            # "Yes, this is real"
            # Currently we don't persist "verified" status, but we could in edge metadata
            console.print("[green]Match confirmed.[/green]")
            i += 1
            processed_count += 1

        elif choice == "s":
            console.print("[dim]Skipped.[/dim]")
            i += 1

        elif choice == "e":
            # Explain why the match happened
            explanation = explainer.explain(edge.source_id, edge.target_id)
            console.print("\n" + explainer.format(explanation) + "\n")
            # Don't increment i, let them vote again after reading explanation

        elif choice == "n":
            # Suppress flow
            suppressed = _handle_suppression(edge, suppression_store)
            if suppressed:
                # If they actually added a rule, we move on
                processed_count += 1
            i += 1

    console.print(f"\n✨ Review complete. Processed {processed_count} items.")

    # Auto-transition to enforcement mode
    if processed_count > 0:
        mode_manager = get_mode_manager()
        mode_manager.mark_review_completed()

        console.print(
            "\n   [bold yellow]Switched to Enforcement Mode[/bold yellow]. "
            "Future scans will use higher confidence thresholds."
        )
        console.print(
            "   Use [cyan]jnkn scan --mode discovery[/cyan] to see all potential connections again."
        )


def _print_edge_panel(edge, current, total):
    """Render a pretty panel for the edge."""
    # Colorize IDs based on type prefix for readability
    src_color = "cyan"
    if edge.source_id.startswith("env:"):
        src_color = "yellow"

    tgt_color = "magenta"
    if edge.target_id.startswith("infra:"):
        tgt_color = "magenta"

    content = f"""
[bold {src_color}]Source:[/bold {src_color}] {edge.source_id}
[bold {tgt_color}]Target:[/bold {tgt_color}] {edge.target_id}
[bold]Type:[/bold]   {edge.type}
[bold]Score:[/bold]  {edge.confidence:.2f}
    """
    console.print(Panel(content.strip(), title=f"Match {current}/{total}", expand=False))


def _handle_suppression(edge, store) -> bool:
    """
    Interactive sub-menu for choosing suppression strategy.

    Returns:
        bool: True if a suppression was added, False if cancelled.
    """
    src_patterns = suggest_patterns(edge.source_id)
    tgt_patterns = suggest_patterns(edge.target_id)

    # Get the broadest meaningful pattern (usually the last or second to last)
    broad_src = src_patterns[-1]
    broad_tgt = tgt_patterns[-1]

    console.print("\n[bold]How wide should this suppression rule be?[/bold]")

    # Option 1: Exact
    console.print("\n[bold cyan]1. Just this specific link[/bold cyan] (Safest)")
    console.print(f"   [dim]Block only:[/dim] {edge.source_id} -> {edge.target_id}")

    # Option 2: Source Wildcard
    console.print("\n[bold cyan]2. Ignore this Source Pattern[/bold cyan]")
    console.print(f"   [dim]Block:[/dim]      [yellow]{broad_src}[/yellow] -> {edge.target_id}")
    console.print(
        f"   [dim]Meaning:[/dim]    [italic]Nothing matching '{broad_src}' should ever link to this target.[/italic]"
    )

    # Option 3: Target Wildcard
    console.print("\n[bold cyan]3. Ignore this Target Pattern[/bold cyan]")
    console.print(f"   [dim]Block:[/dim]      {edge.source_id} -> [magenta]{broad_tgt}[/magenta]")
    console.print(
        f"   [dim]Meaning:[/dim]    [italic]This source should never link to anything matching '{broad_tgt}'.[/italic]"
    )

    # Option 4: Full Wildcard
    console.print("\n[bold cyan]4. Ignore this Pattern entirely[/bold cyan] (Broadest)")
    console.print(
        f"   [dim]Block:[/dim]      [yellow]{broad_src}[/yellow] -> [magenta]{broad_tgt}[/magenta]"
    )
    console.print(
        "   [dim]Meaning:[/dim]    [italic]Never link these two types of things together.[/italic]"
    )

    console.print("\n[dim]c. Cancel[/dim]")

    choice = Prompt.ask("Choose scope", choices=["1", "2", "3", "4", "c"], default="1")

    if choice == "c":
        return False

    s_pat, t_pat = edge.source_id, edge.target_id

    if choice == "2":
        s_pat = broad_src
    elif choice == "3":
        t_pat = broad_tgt
    elif choice == "4":
        s_pat = broad_src
        t_pat = broad_tgt

    reason = Prompt.ask("Reason (optional)")

    store.add(s_pat, t_pat, reason=reason, created_by="interactive_review")
    store.save()

    console.print(f"[green]🚫 Suppressed pattern: {s_pat} -> {t_pat}[/green]\n")
    return True
