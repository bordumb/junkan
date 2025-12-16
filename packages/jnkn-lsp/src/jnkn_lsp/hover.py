"""
Hover Logic.

Provides rich tooltips showing infrastructure connections.
"""

from typing import Optional

from lsprotocol.types import Hover, MarkupContent, MarkupKind, Position

from .manager import LspGraphManager
from .utils import format_hover_markdown, uri_to_path


def resolve_hover(
    uri: str,
    position: Position,
    graph_manager: LspGraphManager
) -> Optional[Hover]:
    """
    Handle textDocument/hover request.

    Args:
        uri: Document URI.
        position: Cursor position (line, character).
        graph_manager: The graph state manager.

    Returns:
        Hover | None: Hover content if a relevant node is found.
    """
    file_path = uri_to_path(uri)
    nodes = graph_manager.get_nodes_in_file(file_path)
    
    target_node = _find_node_at_position(nodes, position.line)
    
    if not target_node:
        return None

    provider = graph_manager.get_provider(target_node.id)
    
    if not provider:
        return None

    # Construct hover content
    content = format_hover_markdown(
        node_name=target_node.name,
        resource_address=provider.name,
        node_type=provider.type.value
    )

    return Hover(
        contents=MarkupContent(
            kind=MarkupKind.Markdown,
            value=content
        )
    )


def _find_node_at_position(nodes: list, line: int) -> Optional[object]:
    """
    Find the specific node at the given line number.
    
    Note: Metadata stores 1-based lines, LSP uses 0-based.
    
    Args:
        nodes: List of Node objects.
        line: 0-based line number from LSP.

    Returns:
        Node | None: The matching node.
    """
    for node in nodes:
        node_line = node.metadata.get("line")
        if node_line is not None and (node_line - 1) == line:
            return node
    return None