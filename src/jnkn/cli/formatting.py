"""
CLI Formatting Utilities.

This module handles the "polish" of CLI output, ensuring that complex
graph data is presented in a readable, grouped, and visually appealing way.
It separates presentation logic from command execution logic.
"""

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

import click

# Display configuration for different artifact domains
# Format: (Label, Emoji, Color)
DOMAIN_STYLES = {
    "python": ("Python Code", "🐍", "green"),
    "javascript": ("JavaScript/TypeScript", "⚡", "yellow"),
    "terraform": ("Terraform", "🏗️", "magenta"),
    "kubernetes": ("Kubernetes", "☸️", "blue"),
    "data": ("Data Assets", "📊", "cyan"),
    "config": ("Configuration", "🔧", "red"),
    "other": ("Other Artifacts", "📦", "white"),
}


def _get_domain(artifact_id: str) -> str:
    """
    Determine the display domain for an artifact ID.
    """
    if artifact_id.startswith("env:"):
        return "config"
    if artifact_id.startswith("infra:"):
        return "terraform"
    if artifact_id.startswith("k8s:"):
        return "kubernetes"
    if artifact_id.startswith("data:"):
        return "data"

    if artifact_id.startswith("file://"):
        path = artifact_id.replace("file://", "")
        ext = Path(path).suffix.lower()
        if ext in (".py", ".pyi"):
            return "python"
        if ext in (".js", ".ts", ".jsx", ".tsx", ".mjs"):
            return "javascript"
        if ext in (".tf", ".hcl"):
            return "terraform"
        if ext in (".yaml", ".yml") and ("k8s" in path or "deploy" in path):
            return "kubernetes"

    return "other"


def format_blast_radius(result: Dict[str, Any]) -> str:
    """
    Format blast radius results into a visual report.

    Args:
        result: Dictionary returned by BlastRadiusAnalyzer.calculate()

    Returns:
        Formatted string ready for printing.
    """
    lines = []

    # Header
    lines.append("")
    lines.append(f"💥 {click.style('Blast Radius Analysis', bold=True)}")
    lines.append("════" + "═" * 20)

    # Source
    sources = result.get("source_artifacts", [])
    source_text = ", ".join(sources)
    lines.append(f"Source: {click.style(source_text, fg='cyan')}")
    lines.append("")

    impacted = result.get("impacted_artifacts", [])
    if not impacted:
        lines.append(click.style("✅ No downstream dependencies found.", dim=True))
        return "\n".join(lines)

    # Group by domain
    grouped: Dict[str, List[str]] = defaultdict(list)
    for artifact in impacted:
        domain = _get_domain(artifact)
        grouped[domain].append(artifact)

    # Sort groups for consistent display order
    # Priority: Config -> Code -> Infra -> Data -> K8s
    priority = ["config", "python", "javascript", "terraform", "kubernetes", "data", "other"]
    sorted_domains = sorted(
        grouped.keys(), key=lambda k: priority.index(k) if k in priority else 99
    )

    for domain in sorted_domains:
        items = sorted(grouped[domain])
        label, emoji, color = DOMAIN_STYLES.get(domain, DOMAIN_STYLES["other"])

        count = len(items)
        header = f"{emoji}  {label} ({count})"
        lines.append(click.style(header, bold=True, fg=color))

        for item in items:
            # Clean up the display name
            display_name = item
            if item.startswith("file://"):
                display_name = item.replace("file://", "")
            elif item.startswith("infra:"):
                display_name = item.replace("infra:", "")
            elif item.startswith("env:"):
                display_name = item.replace("env:", "")

            lines.append(f"  • {display_name}")

        lines.append("")  # Spacer between groups

    return "\n".join(lines)
