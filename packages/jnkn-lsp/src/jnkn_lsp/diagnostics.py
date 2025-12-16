"""
Diagnostic Logic ("Squigglies").

Analyzes files for broken dependencies and orphan nodes.
"""

from typing import List, Optional

from pygls.lsp.server import LanguageServer
from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, PublishDiagnosticsParams, Range

from jnkn.core.types import Node
from .manager import LspGraphManager
from .utils import uri_to_path


def generate_diagnostics(ls: LanguageServer, uri: str, graph_manager: LspGraphManager) -> None:
    """
    Analyze a document and publish diagnostics to the client.

    Args:
        ls: The Language Server instance.
        uri: The URI of the document to analyze.
        graph_manager: The graph state manager.
    """
    file_path = uri_to_path(uri)
    nodes = graph_manager.get_nodes_in_file(file_path)
    diagnostics: List[Diagnostic] = []

    for node in nodes:
        orphan_diag = _check_orphan(node, graph_manager)
        if orphan_diag:
            diagnostics.append(orphan_diag)

    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
    )


def _check_orphan(node: Node, graph_manager: LspGraphManager) -> Optional[Diagnostic]:
    """
    Check if a node is an orphan (Check 1).

    Args:
        node: The node to analyze.
        graph_manager: The graph state manager.

    Returns:
        Diagnostic | None: A diagnostic object if the node is orphaned.
    """
    if not graph_manager.is_orphan(node):
        return None

    # Determine line number (1-based in metadata, 0-based in LSP)
    line = node.metadata.get("line", 1) - 1
    
    # Simple range estimation (whole line if specific cols missing)
    rng = Range(
        start=Position(line=line, character=0),
        end=Position(line=line, character=80),
    )

    return Diagnostic(
        range=rng,
        message=f"Orphaned Environment Variable: '{node.name}' has no infrastructure provider.",
        severity=DiagnosticSeverity.Error,
        source="jnkn",
        code="orphan-var",
    )