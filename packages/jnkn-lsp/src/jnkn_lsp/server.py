"""
LSP Server implementation for Jnkn.

This server acts as the bridge between the IDE (VS Code) and the Jnkn graph engine.
It uses pygls to handle the Language Server Protocol.
"""

import logging
from typing import Optional

from lsprotocol.types import (
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_HOVER,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    Hover,
    HoverParams,
    InitializeParams,
    MarkupContent,
    MarkupKind,
    PublishDiagnosticsParams,
)
from pygls.lsp.server import LanguageServer

from jnkn_lsp.graph import LspGraphManager
from jnkn_lsp.utils import uri_to_path
from jnkn_lsp.workspace import WorkspaceManager

# Setup basic logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("jnkn-lsp")

server = LanguageServer("jnkn-lsp", "v0.1.0")

# Global state managers
graph_manager: Optional[LspGraphManager] = None
workspace_manager: Optional[WorkspaceManager] = None


@server.feature("initialize")
def initialize(params: InitializeParams):
    """
    Handle the initialization request from the client.
    Auto-bootstraps the database and watcher process.
    """
    global graph_manager, workspace_manager

    root_uri = params.root_uri or params.root_path
    if not root_uri:
        logger.warning("No root URI provided. LSP functionality limited.")
        return

    logger.info(f"Initializing Jnkn LSP for root: {root_uri}")

    # 1. Setup Workspace (Init DB, Scan, Start Watcher)
    workspace_manager = WorkspaceManager(root_uri)
    workspace_manager.setup()

    # 2. Setup Graph Connection (Read-Only)
    graph_manager = LspGraphManager(workspace_manager.db_path)

    logger.info("LSP Initialization complete.")


@server.feature("shutdown")
def shutdown(params):
    """Handle the shutdown request."""
    global workspace_manager
    if workspace_manager:
        workspace_manager.teardown()


@server.feature(TEXT_DOCUMENT_DID_OPEN)
async def did_open(ls: LanguageServer, params: DidOpenTextDocumentParams):
    """Handle file open events by triggering diagnostics."""
    uri = params.text_document.uri
    await _publish_diagnostics(ls, uri)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
async def did_save(ls: LanguageServer, params: DidSaveTextDocumentParams):
    """Handle file save events."""
    uri = params.text_document.uri
    await _publish_diagnostics(ls, uri)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: HoverParams) -> Optional[Hover]:
    """Handle hover events."""
    if not graph_manager:
        return None

    uri = params.text_document.uri
    line = params.position.line

    # Convert URI to absolute path (DB stores absolute paths)
    abs_path = uri_to_path(uri)
    file_path_str = str(abs_path)

    node_info = graph_manager.get_hover_info(file_path_str, line)

    if not node_info:
        return None

    markdown_content = (
        f"**Jnkn Linkage**\n\n"
        f"**Artifact:** `{node_info['name']}`\n"
        f"**Type:** `{node_info['type']}`\n"
        f"**Connected Infra:** `{node_info['provider']}`\n\n"
        f"[View in Graph](command:jnkn.showGraph)"
    )

    return Hover(
        contents=MarkupContent(kind=MarkupKind.Markdown, value=markdown_content)
    )


async def _publish_diagnostics(ls: LanguageServer, uri: str):
    """Helper to run orphan detection diagnostics."""
    if not graph_manager or not workspace_manager:
        return

    # Convert URI to absolute path (DB stores absolute paths)
    abs_path = uri_to_path(uri)
    file_path_str = str(abs_path)

    logger.info(f"Publishing diagnostics for: {file_path_str}")

    diagnostics = graph_manager.get_diagnostics(file_path_str)

    logger.info(f"Found {len(diagnostics)} diagnostics")

    ls.text_document_publish_diagnostics(
        PublishDiagnosticsParams(uri=uri, diagnostics=diagnostics)
    )


def main():
    """Entry point for the LSP server."""
    server.start_io()


if __name__ == "__main__":
    main()
