"""
Graph data access layer for the Jnkn LSP.

This module handles all direct interactions with the SQLite database.
It is designed to be read-only and resilient to database locks or missing tables.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any

from lsprotocol.types import Diagnostic, DiagnosticSeverity, Position, Range

from jnkn.core.types import NodeType, RelationshipType

logger = logging.getLogger(__name__)

# Node types that represent "consumer" artifacts (depend on infrastructure providers)
CONSUMER_NODE_TYPES: tuple[str, ...] = (
    NodeType.ENV_VAR.value,
    NodeType.CONFIG_KEY.value,
)


class LspGraphManager:
    """
    Manages read-only access to the Jnkn dependency graph.

    This class abstracts the SQL queries required to support LSP features
    like Hover (context) and Diagnostics (orphan detection).

    Attributes:
        db_path: Absolute path to the .jnkn/jnkn.db SQLite file.
    """

    def __init__(self, db_path: Path) -> None:
        """
        Initialize the graph manager.

        Args:
            db_path: Absolute path to the .jnkn/jnkn.db SQLite file.
        """
        self.db_path = db_path

    def _get_connection(self) -> sqlite3.Connection:
        """
        Create a connection to the database that can read WAL changes.

        SQLite WAL mode requires special handling for read-only access:
        - mode=ro alone may not see uncommitted WAL changes
        - We use a regular connection with PRAGMA query_only for safety
        - This allows reading the latest WAL data while preventing writes

        Returns:
            A SQLite connection configured for read-only access with WAL support.
        """
        # Use a regular connection (not URI mode=ro) to properly read WAL
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        
        # Set to read-only mode via PRAGMA (safer than file permissions)
        conn.execute("PRAGMA query_only = ON")
        
        # Ensure we read the latest WAL data
        conn.execute("PRAGMA read_uncommitted = ON")
        
        return conn

    def get_hover_info(
        self, file_path: str, line_number: int
    ) -> dict[str, Any] | None:
        """
        Retrieve graph context for a specific line in a file.

        Args:
            file_path: The absolute path of the file.
            line_number: The 0-indexed line number from the editor.

        Returns:
            Dict containing node details and its upstream provider, or None.
        """
        if not self.db_path.exists():
            return None

        # Query using exact path match (DB stores absolute paths)
        query = """
            SELECT
                n.id,
                n.name,
                n.type,
                provider.name as provider_name,
                provider.type as provider_type
            FROM nodes n
            LEFT JOIN edges e ON n.id = e.target_id AND e.type = ?
            LEFT JOIN nodes provider ON e.source_id = provider.id
            WHERE n.path = ?
              AND json_extract(n.metadata, '$.line') = ?
            LIMIT 1
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Editor lines are 0-indexed, parsers store 1-indexed
                cursor.execute(query, (RelationshipType.PROVIDES.value, file_path, line_number + 1))
                row = cursor.fetchone()

                if row:
                    node_id, name, node_type, prov_name, prov_type = row
                    return {
                        "id": node_id,
                        "name": name,
                        "type": node_type,
                        "provider": prov_name if prov_name else "None",
                    }
        except sqlite3.Error as e:
            logger.error(f"Database error during hover: {e}")
            return None

        return None

    def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """
        Analyze a file for architectural violations.

        Currently implements 'Orphan Detection': identifies environment variables
        and configuration keys that have no 'provides' edge from infrastructure.

        An orphan is a consumer node (env_var, config_key) that has no incoming
        'provides' edge. Note: 'reads' edges from code files don't count as providers.

        Args:
            file_path: The absolute path to analyze.

        Returns:
            A list of LSP Diagnostic objects.
        """
        if not self.db_path.exists():
            logger.warning(f"Database not found: {self.db_path}")
            return []

        diagnostics: list[Diagnostic] = []

        # Build the IN clause using canonical values from NodeType enum
        type_placeholders = ", ".join("?" for _ in CONSUMER_NODE_TYPES)

        # Query for nodes that have NO incoming 'provides' edge
        # The key change: filter edges by type = 'provides' in the LEFT JOIN
        query = f"""
            SELECT
                n.id,
                n.name,
                n.type,
                json_extract(n.metadata, '$.line') as line_num
            FROM nodes n
            LEFT JOIN edges e ON n.id = e.target_id AND e.type = ?
            WHERE n.path = ?
              AND n.type IN ({type_placeholders})
              AND e.source_id IS NULL
        """

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Parameters: provides edge type, file path, then consumer node types
                params = (RelationshipType.PROVIDES.value, file_path, *CONSUMER_NODE_TYPES)
                logger.info(f"Running orphan query with path: {file_path}")
                cursor.execute(query, params)
                rows = cursor.fetchall()

                logger.info(f"Orphan query returned {len(rows)} results")

                for row in rows:
                    node_id, name, node_type, line_num = row

                    if not line_num:
                        logger.warning(f"Node '{name}' missing line number, skipping")
                        continue

                    line_idx = int(line_num) - 1
                    start_pos = Position(line=line_idx, character=0)
                    end_pos = Position(line=line_idx, character=80)

                    diagnostic = Diagnostic(
                        range=Range(start=start_pos, end=end_pos),
                        message=f"Orphaned Environment Variable: '{name}' has no infrastructure provider.",
                        severity=DiagnosticSeverity.Error,
                        source="jnkn",
                        code="orphan-var",
                    )
                    diagnostics.append(diagnostic)
                    logger.info(f"Created diagnostic for orphan: {name}")

        except sqlite3.Error as e:
            logger.error(f"Database error during diagnostics: {e}")
            return []

        return diagnostics