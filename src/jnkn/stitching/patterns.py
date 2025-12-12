"""
Pattern generation logic for interactive suppression suggestions.

This module provides heuristics to generate valid glob patterns from specific
node identifiers. It is used by the `review` command to offer users
broad but safe suppression rules (e.g., suppressing all `*_ID` matches
rather than just one specific ID).
"""

from typing import List


def suggest_patterns(node_id: str) -> List[str]:
    """
    Generate glob patterns for a given node ID.

    Analyzes the structure of the node ID (prefix, separators, common suffixes)
    to suggest wildcards that would match similar nodes.

    Args:
        node_id: The full node identifier (e.g., "env:PAYMENT_API_KEY").

    Returns:
        List[str]: A list of suggested patterns, starting with the exact match
        and moving towards more generic patterns.

    Example:
        >>> suggest_patterns("env:PAYMENT_API_KEY")
        ['env:PAYMENT_API_KEY', 'env:PAYMENT_*', 'env:*_KEY']
    """
    suggestions = [node_id]  # Always offer exact match first

    # If not a structured ID (no colon), return just the ID (or maybe just *)
    if ":" not in node_id:
        return suggestions

    prefix, name = node_id.split(":", 1)

    # Strategy 1: Dot Separation (Terraform Resource Types / Object Properties)
    # e.g., infra:aws_db_instance.payment -> infra:aws_db_instance.*
    # This is critical for infrastructure where type.name is the standard convention.
    if "." in name:
        base = name.split(".")[0]
        if base:
            suggestions.append(f"{prefix}:{base}.*")

    # Strategy 2: Underscore Prefix (Common for lists/groups)
    # e.g., env:PAYMENT_HOST -> env:PAYMENT_*
    if "_" in name:
        base = name.split("_")[0]
        # Avoid creating a pattern like "env:*_" if base is empty
        if base:
            suggestions.append(f"{prefix}:{base}_*")

    # Strategy 3: Suffix Wildcard (Common for semantic types)
    # e.g., env:PAYMENT_ID -> env:*_ID
    # We check for specific, high-noise suffixes
    common_suffixes = [
        "_ID",
        "_KEY",
        "_SECRET",
        "_TOKEN",
        "_URL",
        "_HOST",
        "_PORT",
        "_ARN",
        "_NAME",
    ]

    for suffix in common_suffixes:
        if name.endswith(suffix):
            suggestions.append(f"{prefix}:*{suffix}")
            break

    # Strategy 4: Generic prefix wildcard
    # e.g. env:VAR -> env:*
    # We append this last as it is the broadest
    suggestions.append(f"{prefix}:*")

    # Deduplicate while preserving order
    seen = set()
    unique_suggestions = []
    for s in suggestions:
        if s not in seen:
            unique_suggestions.append(s)
            seen.add(s)

    return unique_suggestions
