"""
LSP Utilities.

Helper functions for URI handling and path normalization.
"""

import urllib.parse
from pathlib import Path


def uri_to_path(uri: str) -> Path:
    """
    Convert an LSP URI to a local file system path.

    Args:
        uri: The URI string (e.g., 'file:///Users/marcus/code/app.py').

    Returns:
        Path: The corresponding Path object.
    """
    parsed = urllib.parse.urlparse(uri)
    path_str = urllib.parse.unquote(parsed.path)
    return Path(path_str).resolve()


def format_hover_markdown(node_name: str, resource_address: str, node_type: str) -> str:
    """
    Format the hover text content using Markdown.

    Args:
        node_name: The name of the node (e.g., 'DB_HOST').
        resource_address: The connected infrastructure address.
        node_type: The type of the node.

    Returns:
        str: Formatted Markdown string.
    """
    return f"""### Jnkn Linkage
**Artifact:** `{node_name}`
**Type:** `{node_type}`
**Connected Infra:** `{resource_address}`

[View in Graph](command:jnkn.visualize)
"""