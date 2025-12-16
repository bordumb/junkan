"""
Graph State Manager.

Handles loading and querying the dependency graph for the LSP server.
Optimized for read-only access to the SQLite database maintained by the Watcher.
"""

import logging
import os
from pathlib import Path
from typing import List, Optional

from jnkn.core.graph import DependencyGraph
from jnkn.core.storage.sqlite import SQLiteStorage
from jnkn.core.types import Node, NodeType

# Configure logger to ensure visibility in VS Code Output panel
logger = logging.getLogger("jnkn-lsp")
logger.setLevel(logging.INFO)


class LspGraphManager:
    """
    Manages the dependency graph lifecycle for the Language Server.

    This class acts as the interface between the stateless LSP requests
    and the stateful SQLite database maintained by the 'jnkn watch' daemon.
    """

    def __init__(self, db_path: Path = Path(".jnkn/jnkn.db")):
        """
        Initialize the graph manager.

        Args:
            db_path: Path to the SQLite database file. Defaults to .jnkn/jnkn.db.
        """
        # Resolve absolute path immediately to avoid CWD ambiguity in VS Code
        self.db_path = db_path.resolve()
        
        logger.info(f"🔍 LSP Manager Initialized.")
        logger.info(f"   Looking for DB at: {self.db_path}")
        logger.info(f"   Current Working Dir: {os.getcwd()}")
        
        self._graph: Optional[DependencyGraph] = None
        self._storage: Optional[SQLiteStorage] = None

    def get_graph(self) -> DependencyGraph:
        """
        Retrieve the current dependency graph, reloading from disk if necessary.

        Ideally, this relies on the separate 'jnkn watch' process to update the DB.
        The LSP simply reads the latest state using SQLite WAL mode for concurrency.

        Returns:
            DependencyGraph: The loaded graph instance.
        """
        # 1. Log the attempt so you know the LSP is trying to read
        logger.info(f"🔄 LSP attempting to read DB at: {self.db_path}")

        if not self.db_path.exists():
            # CRITICAL: This log helps you catch if the watcher is writing to a different path
            logger.error(f"❌ Database NOT FOUND at {self.db_path}")
            logger.error(f"   Please ensure 'jnkn watch' is running in the root: {self.db_path.parent}")
            return DependencyGraph()

        try:
            # Force close to release any stale locks
            if self._storage:
                self._storage.close()

            self._storage = SQLiteStorage(self.db_path)
            self._graph = self._storage.load_graph()
            
            logger.info(f"✅ Loaded Graph: {self._graph.node_count} nodes")
            return self._graph
        except Exception as e:
            logger.error(f"❌ Failed to load graph: {e}", exc_info=True)
            return DependencyGraph()

    def get_nodes_in_file(self, file_path: Path) -> List[Node]:
        """
        Find all nodes defined in a specific file.

        Used to determine which artifacts (e.g., Env Vars) are present in the
        currently open document to run diagnostics on them.

        Args:
            file_path: Absolute path to the file.

        Returns:
            List[Node]: Nodes originating from this file.
        """
        graph = self.get_graph()
        path_str = str(file_path)
        
        # Simple heuristic matching: check if node path suffix matches file path
        found = [
            node for node in graph.iter_nodes()
            if node.path and path_str.endswith(node.path)
        ]
        
        logger.info(f"   Found {len(found)} nodes for file: {file_path.name}")
        return found

    def get_provider(self, node_id: str) -> Optional[Node]:
        """
        Find the upstream provider for a given node.

        Used for Hover support to show what infrastructure provides a value.

        Args:
            node_id: The ID of the consumer node.

        Returns:
            Node | None: The upstream node if one exists.
        """
        graph = self.get_graph()
        in_edges = graph.get_in_edges(node_id)
        
        for edge in in_edges:
            source = graph.get_node(edge.source_id)
            if source:
                return source
        return None

    def is_orphan(self, node: Node) -> bool:
        """
        Check if an environment variable node has no INFRASTRUCTURE providers.

        An orphan is defined as an ENV_VAR node that lacks a 'provides' or
        'provisions' relationship from an upstream source.

        Args:
            node: The node to check.

        Returns:
            bool: True if the node is an orphaned ENV_VAR.
        """
        if node.type != NodeType.ENV_VAR:
            return False

        graph = self.get_graph()
        in_edges = graph.get_in_edges(node.id)
        
        # DEBUG: Log edges for this node
        logger.info(f"DEBUG: Checking orphan status for {node.name} (Edges: {len(in_edges)})")
        
        # Look for at least one edge with type 'provides' or 'provisions'
        # This prevents false positives from 'reads' edges (File -> EnvVar)
        has_provider = any(
            edge.type == "provides" or edge.type == "provisions" 
            for edge in in_edges
        )
        
        return not has_provider