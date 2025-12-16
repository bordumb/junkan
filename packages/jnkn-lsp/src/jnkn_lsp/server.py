"""
LSP Server Entry Point.

Configures and runs the pygls Language Server.
"""

import logging
import sys
from typing import Optional

from pygls.lsp.server import LanguageServer
from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_HOVER,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Hover,
    HoverParams,
    ShowMessageParams, 
    MessageType
)

from .diagnostics import generate_diagnostics
from .hover import resolve_hover
from .manager import LspGraphManager

# Configure logging to write to stderr so VS Code Output Panel captures it
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

# Initialize Server
server = LanguageServer("jnkn-lsp", "v0.0.0-rc.1")
graph_manager = LspGraphManager()


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams):
    """
    Handle document open event.
    Triggers diagnostic check.
    """
    # Log to Output panel for debugging
    logging.info(f"📂 Opened: {params.text_document.uri}")
    
    # Send toast to user (optional, can be noisy)
    ls.window_show_message(
        ShowMessageParams(
            message=f"Jnkn LSP: Analyzing {params.text_document.uri}",
            type=MessageType.Info,
        )
    )
    
    generate_diagnostics(ls, params.text_document.uri, graph_manager)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: LanguageServer, params: DidSaveTextDocumentParams):
    """
    Handle document save event.
    Triggers diagnostic check after graph update (handled by Watcher or reload).
    """
    logging.info(f"💾 Saved: {params.text_document.uri}")
    generate_diagnostics(ls, params.text_document.uri, graph_manager)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: HoverParams) -> Optional[Hover]:
    """
    Handle hover event.
    Returns details about the connected infrastructure node.
    """
    # Debug log for hover (helpful to ensure coordinates are correct)
    logging.info(f"🔍 Hover at {params.position.line}:{params.position.character}")
    
    return resolve_hover(
        params.text_document.uri,
        params.position,
        graph_manager
    )


def main():
    """Entry point for the LSP server."""
    server.start_io()


if __name__ == "__main__":
    main()