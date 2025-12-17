"""
Graph Manager for the Jnkn LSP.

Manages read-only access to the dependency graph stored in SQLite,
providing data for LSP features like hover information and diagnostics.

Enhanced with support for explicit mappings from jnkn.toml:
- Ignored sources are filtered from orphan diagnostics
- Explicit mappings are respected when determining orphan status
- Related locations show where breaking changes occurred
"""

import logging
import sqlite3
from pathlib import Path
from typing import Any, Optional, Set

from lsprotocol.types import (
    Diagnostic,
    DiagnosticRelatedInformation,
    DiagnosticSeverity,
    Location,
    Position,
    Range,
)

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

    Supports explicit mappings from jnkn.toml:
    - IGNORE mappings suppress orphan warnings for specified nodes
    - PROVIDES mappings create edges that prevent orphan status
    - Related locations point to where breaking changes may have occurred

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
        self._ignored_sources_cache: Optional[Set[str]] = None

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
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.execute("PRAGMA query_only = ON")
        conn.execute("PRAGMA read_uncommitted = ON")
        return conn

    def _get_ignored_sources(self) -> Set[str]:
        """
        Load the set of ignored source patterns from jnkn.toml.

        Returns:
            Set of source node IDs/patterns that should not trigger diagnostics.
        """
        manifest_path = self.db_path.parent.parent / "jnkn.toml"

        if not manifest_path.exists():
            return set()

        try:
            from jnkn.core.manifest import ProjectManifest

            manifest = ProjectManifest.load(manifest_path)
            ignored = set(manifest.get_ignored_sources())
            logger.debug(f"Loaded {len(ignored)} ignored sources from manifest")
            return ignored

        except Exception as e:
            logger.warning(f"Failed to load manifest for ignore list: {e}")
            return set()

    def _get_expected_providers(self) -> dict[str, str]:
        """
        Load explicit mappings to know which provider each target expects.

        Returns:
            Dict mapping target node IDs to their expected source node IDs.
        """
        manifest_path = self.db_path.parent.parent / "jnkn.toml"

        if not manifest_path.exists():
            return {}

        try:
            from jnkn.core.manifest import ProjectManifest, MappingType

            manifest = ProjectManifest.load(manifest_path)
            expected = {}

            for mapping in manifest.mappings:
                if mapping.mapping_type != MappingType.IGNORE and mapping.target:
                    expected[mapping.target] = mapping.source

            return expected

        except Exception as e:
            logger.warning(f"Failed to load mappings: {e}")
            return {}

    def _is_ignored(self, node_id: str, name: str) -> bool:
        """
        Check if a node should be ignored in diagnostics.

        Args:
            node_id: The full node ID (e.g., "env:DATABASE_URL").
            name: The node name (e.g., "DATABASE_URL").

        Returns:
            True if the node is in the ignore list.
        """
        ignored = self._get_ignored_sources()

        if node_id in ignored:
            return True
        if f"env:{name}" in ignored:
            return True
        if name in ignored:
            return True

        return False

    def invalidate_cache(self) -> None:
        """Invalidate the ignored sources cache."""
        self._ignored_sources_cache = None

    def get_hover_info(self, file_path: str, line_number: int) -> dict[str, Any] | None:
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

        query = """
            SELECT
                n.id,
                n.name,
                n.type,
                provider.name as provider_name,
                provider.type as provider_type,
                e.confidence as edge_confidence,
                e.metadata as edge_metadata
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
                cursor.execute(
                    query, (RelationshipType.PROVIDES.value, file_path, line_number + 1)
                )
                row = cursor.fetchone()

                if row:
                    (
                        node_id,
                        name,
                        node_type,
                        prov_name,
                        prov_type,
                        confidence,
                        metadata,
                    ) = row

                    result = {
                        "id": node_id,
                        "name": name,
                        "type": node_type,
                        "provider": prov_name if prov_name else "None",
                    }

                    if confidence is not None:
                        result["confidence"] = confidence

                    if self._is_ignored(node_id, name):
                        result["ignored"] = True
                        result["provider"] = "(ignored - see jnkn.toml)"

                    return result

        except sqlite3.Error as e:
            logger.error(f"Database error during hover: {e}")
            return None

        return None

    def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """
        Analyze a file for architectural violations.

        Implements 'Orphan Detection': identifies environment variables
        and configuration keys that have no 'provides' edge from infrastructure.

        When an explicit mapping exists but the source is missing, includes
        related location information pointing to where the source should be.

        Args:
            file_path: The absolute path to analyze.

        Returns:
            A list of LSP Diagnostic objects with related locations.
        """
        if not self.db_path.exists():
            logger.warning(f"Database not found: {self.db_path}")
            return []

        diagnostics: list[Diagnostic] = []

        # Load explicit mappings to find expected providers
        expected_providers = self._get_expected_providers()

        type_placeholders = ", ".join("?" for _ in CONSUMER_NODE_TYPES)

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
                params = (
                    RelationshipType.PROVIDES.value,
                    file_path,
                    *CONSUMER_NODE_TYPES,
                )
                logger.info(f"Running orphan query with path: {file_path}")
                cursor.execute(query, params)
                rows = cursor.fetchall()

                logger.info(f"Orphan query returned {len(rows)} results")

                for row in rows:
                    node_id, name, node_type, line_num = row

                    # Skip ignored nodes
                    if self._is_ignored(node_id, name):
                        logger.debug(f"Skipping ignored node: {node_id}")
                        continue

                    if not line_num:
                        logger.warning(f"Node '{name}' missing line number, skipping")
                        continue

                    line_idx = int(line_num) - 1
                    start_pos = Position(line=line_idx, character=0)
                    end_pos = Position(line=line_idx, character=80)

                    # Check for expected provider from explicit mapping
                    expected_source = expected_providers.get(
                        node_id
                    ) or expected_providers.get(f"env:{name}")
                    related_info = []
                    message = f"Orphaned Environment Variable: '{name}' has no infrastructure provider."

                    if expected_source:
                        # There was an explicit mapping - the source is missing!
                        # Try to find where the source should have been
                        similar_location = self._find_similar_provider(
                            conn, expected_source
                        )

                        if similar_location:
                            sim_path, sim_line, sim_name, git_url = similar_location

                            # Build message with GitHub link if available
                            if git_url:
                                message = (
                                    f"Breaking Change Detected: '{name}' expects provider "
                                    f"'{expected_source}' which no longer exists. "
                                    f"Found similar output '{sim_name}' - was it renamed?\n"
                                    f"🔗 View on GitHub: {git_url}"
                                )
                            else:
                                message = (
                                    f"Breaking Change Detected: '{name}' expects provider "
                                    f"'{expected_source}' which no longer exists. "
                                    f"Found similar output '{sim_name}' - was it renamed?"
                                )

                            # Also add local file reference for quick navigation
                            related_info.append(
                                DiagnosticRelatedInformation(
                                    location=Location(
                                        uri=f"file://{sim_path}",
                                        range=Range(
                                            start=Position(
                                                line=max(0, sim_line - 1), character=0
                                            ),
                                            end=Position(
                                                line=max(0, sim_line - 1), character=80
                                            ),
                                        ),
                                    ),
                                    message=f"📁 Local cache: Found similar output '{sim_name}'",
                                )
                            )
                        else:
                            message = (
                                f"Breaking Change Detected: '{name}' expects provider "
                                f"'{expected_source}' which no longer exists."
                            )

                            # Try to find the file that should contain it
                            source_file = self._find_source_file(conn, expected_source)
                            if source_file:
                                related_info.append(
                                    DiagnosticRelatedInformation(
                                        location=Location(
                                            uri=f"file://{source_file}",
                                            range=Range(
                                                start=Position(line=0, character=0),
                                                end=Position(line=0, character=80),
                                            ),
                                        ),
                                        message=f"Expected '{expected_source}' to be defined here",
                                    )
                                )

                    diagnostic = Diagnostic(
                        range=Range(start=start_pos, end=end_pos),
                        message=message,
                        severity=DiagnosticSeverity.Error,
                        source="jnkn",
                        code="orphan-var",
                        related_information=related_info if related_info else None,
                    )
                    diagnostics.append(diagnostic)
                    logger.info(f"Created diagnostic for orphan: {name}")

        except sqlite3.Error as e:
            logger.error(f"Database error during diagnostics: {e}")
            return []

        return diagnostics

    def _find_similar_provider(
        self, conn: sqlite3.Connection, expected_source: str
    ) -> Optional[tuple[str, int, str, Optional[str]]]:
        """
        Find a provider in the same repo that might be a renamed version.

        Args:
            conn: Database connection.
            expected_source: The expected source node ID (e.g., "platform:output:datadog_api_endpoint").

        Returns:
            Tuple of (file_path, line_number, node_name, git_web_url) or None.
        """
        parts = expected_source.split(":")
        if len(parts) < 2:
            return None

        repo_prefix = parts[0]  # e.g., "platform"
        expected_name = (
            parts[-1] if len(parts) > 2 else ""
        )  # e.g., "datadog_api_endpoint"

        # Find outputs in the same repo
        # Note: Terraform outputs are stored as 'config_key' type with 'output' in the id
        query = """
            SELECT path, json_extract(metadata, '$.line') as line_num, name, id
            FROM nodes
            WHERE source_repo = ?
              AND id LIKE '%output%'
            ORDER BY name
        """

        try:
            cursor = conn.cursor()
            cursor.execute(query, (repo_prefix,))
            rows = cursor.fetchall()

            logger.info(f"Found {len(rows)} outputs in repo '{repo_prefix}'")

            # Try to find the most similar name
            best_match = None
            best_score = 0

            for path, line_num, name, node_id in rows:
                if not path or not line_num:
                    continue

                # Simple similarity: count matching words
                expected_words = set(expected_name.lower().replace("_", " ").split())
                actual_words = set(name.lower().replace("_", " ").split())
                common = len(expected_words & actual_words)

                logger.debug(f"Comparing '{expected_name}' vs '{name}': score={common}")

                if common > best_score:
                    best_score = common
                    best_match = (path, int(line_num), name)

            # Return best match if we found something reasonable
            if best_match:
                path, line_num, name = best_match
                git_url = self._get_git_web_url(repo_prefix, path, line_num)
                logger.info(
                    f"Best match: {name} at {path}:{line_num}, git_url={git_url}"
                )
                return (path, line_num, name, git_url)

            # Fallback: return first output in the repo
            if rows:
                path, line_num, name, _ = rows[0]
                if path and line_num:
                    git_url = self._get_git_web_url(repo_prefix, path, int(line_num))
                    return (path, int(line_num), name, git_url)

        except sqlite3.Error as e:
            logger.warning(f"Error finding similar provider: {e}")

        return None

    def _get_git_web_url(
        self, repo_name: str, file_path: str, line_num: int
    ) -> Optional[str]:
        """
        Generate a web URL (GitHub/GitLab) for a file in a git dependency.

        Args:
            repo_name: The dependency name (e.g., "platform").
            file_path: Local file path (may be in cache).
            line_num: Line number to link to.

        Returns:
            Web URL string or None if not a git dependency.
        """
        # Load the manifest to get git URL for this dependency
        manifest_path = self.db_path.parent.parent / "jnkn.toml"

        if not manifest_path.exists():
            return None

        try:
            from jnkn.core.manifest import ProjectManifest

            manifest = ProjectManifest.load(manifest_path)

            # Find the dependency
            dep_spec = manifest.dependencies.get(repo_name)
            if not dep_spec or not dep_spec.git:
                return None

            git_url = dep_spec.git
            branch = dep_spec.branch or "main"

            # Convert git URL to web URL
            web_base = self._git_to_web_url(git_url)
            if not web_base:
                return None

            # Extract relative path from the cached path
            # Cache structure: ~/.jnkn/cache/<repo_name>/path/to/file.tf
            relative_path = self._extract_relative_path(file_path, repo_name)
            if not relative_path:
                return None

            # Build the full URL with line number
            # GitHub: /blob/<branch>/<path>#L<line>
            # GitLab: /-/blob/<branch>/<path>#L<line>
            if "gitlab" in web_base.lower():
                return f"{web_base}/-/blob/{branch}/{relative_path}#L{line_num}"
            else:
                # GitHub and others
                return f"{web_base}/blob/{branch}/{relative_path}#L{line_num}"

        except Exception as e:
            logger.warning(f"Failed to generate git web URL: {e}")
            return None

    def _git_to_web_url(self, git_url: str) -> Optional[str]:
        """
        Convert a git remote URL to a web URL.

        Handles:
        - https://github.com/org/repo.git -> https://github.com/org/repo
        - git@github.com:org/repo.git -> https://github.com/org/repo
        - https://gitlab.com/org/repo.git -> https://gitlab.com/org/repo

        Args:
            git_url: The git remote URL.

        Returns:
            Web URL or None.
        """
        import re

        # Remove .git suffix
        url = git_url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        # Handle SSH format: git@github.com:org/repo
        ssh_match = re.match(r"git@([^:]+):(.+)", url)
        if ssh_match:
            host, path = ssh_match.groups()
            return f"https://{host}/{path}"

        # Handle HTTPS format: https://github.com/org/repo
        if url.startswith("https://") or url.startswith("http://"):
            return url

        return None

    def _extract_relative_path(self, file_path: str, repo_name: str) -> Optional[str]:
        """
        Extract the relative path within the repo from a cached file path.

        Args:
            file_path: Full path (e.g., /Users/x/.jnkn/cache/platform/terraform/main.tf)
            repo_name: The repo name (e.g., "platform")

        Returns:
            Relative path (e.g., "terraform/main.tf") or None.
        """
        # Look for the repo name in the path and take everything after it
        parts = file_path.split("/")

        try:
            # Find the repo_name in the path
            idx = parts.index(repo_name)
            # Return everything after repo_name
            relative_parts = parts[idx + 1 :]
            if relative_parts:
                return "/".join(relative_parts)
        except ValueError:
            pass

        # Fallback: just use the filename
        return Path(file_path).name if file_path else None

    def _find_source_file(
        self, conn: sqlite3.Connection, expected_source: str
    ) -> Optional[str]:
        """
        Find the file that should contain the expected source.

        Args:
            conn: Database connection.
            expected_source: The expected source node ID.

        Returns:
            File path or None.
        """
        parts = expected_source.split(":")
        if len(parts) < 2:
            return None

        repo_prefix = parts[0]

        query = """
            SELECT DISTINCT path
            FROM nodes
            WHERE source_repo = ?
              AND path LIKE '%.tf'
            LIMIT 1
        """

        try:
            cursor = conn.cursor()
            cursor.execute(query, (repo_prefix,))
            row = cursor.fetchone()
            if row:
                return row[0]
        except sqlite3.Error:
            pass

        return None

    def get_providers_for_file(self, file_path: str) -> list[dict[str, Any]]:
        """
        Get all provider relationships for nodes in a file.

        Args:
            file_path: The absolute path to analyze.

        Returns:
            List of dicts with consumer/provider info.
        """
        if not self.db_path.exists():
            return []

        query = """
            SELECT
                n.id as consumer_id,
                n.name as consumer_name,
                n.type as consumer_type,
                provider.id as provider_id,
                provider.name as provider_name,
                provider.type as provider_type,
                e.confidence,
                e.metadata
            FROM nodes n
            JOIN edges e ON n.id = e.target_id AND e.type = ?
            JOIN nodes provider ON e.source_id = provider.id
            WHERE n.path = ?
        """

        results = []

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (RelationshipType.PROVIDES.value, file_path))

                for row in cursor.fetchall():
                    (
                        consumer_id,
                        consumer_name,
                        consumer_type,
                        provider_id,
                        provider_name,
                        provider_type,
                        confidence,
                        metadata,
                    ) = row

                    results.append(
                        {
                            "consumer": {
                                "id": consumer_id,
                                "name": consumer_name,
                                "type": consumer_type,
                            },
                            "provider": {
                                "id": provider_id,
                                "name": provider_name,
                                "type": provider_type,
                            },
                            "confidence": confidence,
                        }
                    )

        except sqlite3.Error as e:
            logger.error(f"Database error: {e}")

        return results
