"""
Jnkn AI Context Server.

This module implements a Model Context Protocol (MCP) server that acts as a bridge
between the static analysis graph (Ground Truth) and AI agents (The Navigator).

It exposes core graph primitives as tools, allowing LLMs to:
1. Search the dependency graph.
2. Traverse relationships (neighbors).
3. Analyze file-level impact.
4. Calculate blast radius for specific artifacts.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from jnkn.analysis.blast_radius import BlastRadiusAnalyzer
from jnkn.core.graph import DependencyGraph
from jnkn.core.storage.sqlite import SQLiteStorage
from jnkn.core.types import NodeType

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("jnkn-ai")

# Initialize MCP Server
# Removed 'description' arg which caused TypeError in older fastmcp versions
mcp = FastMCP("Jnkn Context Service")


class GraphManager:
    """
    Manages the lifecycle of the dependency graph for the MCP server.

    Implements lazy loading to ensure the server starts quickly and
    only loads the graph when a request is made.
    """

    def __init__(self, db_path: Path = Path(".jnkn/jnkn.db")):
        self.db_path = db_path
        self._graph: Optional[DependencyGraph] = None
        self._storage: Optional[SQLiteStorage] = None

    def get_graph(self) -> DependencyGraph:
        """
        Retrieve the active dependency graph, loading it if necessary.

        Returns:
            DependencyGraph: The loaded graph instance.

        Raises:
            FileNotFoundError: If the graph database does not exist.
        """
        if self._graph is not None:
            return self._graph

        if not self.db_path.exists():
            # Try to resolve relative to current working directory if explicit path fails
            # This is a fallback for simple usage
            cwd_db = Path.cwd() / ".jnkn" / "jnkn.db"
            if cwd_db.exists():
                self.db_path = cwd_db
            else:
                raise FileNotFoundError(
                    f"Dependency graph not found at {self.db_path}. "
                    "Please run 'jnkn scan' first to generate the graph."
                )

        logger.info(f"Loading graph from {self.db_path}...")
        self._storage = SQLiteStorage(self.db_path)
        self._graph = self._storage.load_graph()
        logger.info(
            f"Graph loaded with {self._graph.node_count} nodes and {self._graph.edge_count} edges."
        )
        return self._graph

    def reload(self):
        """Force a reload of the graph from disk."""
        self._graph = None
        if self._storage:
            self._storage.close()
            self._storage = None


# Global graph manager instance
# In a real deployment, this might be scoped differently or configurable via env vars
_graph_manager = GraphManager()


# --- Models for Tool Outputs ---


class ArtifactNode(BaseModel):
    """Represents a node in the dependency graph."""

    id: str
    name: str
    type: str
    path: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NeighborResult(BaseModel):
    """Result of a neighbor traversal query."""

    node: ArtifactNode
    relationship: str
    direction: str  # "upstream" or "downstream"


class BlastRadiusResult(BaseModel):
    """Result of a blast radius calculation."""

    source_id: str
    impact_count: int
    impacted_nodes: List[str]
    breakdown: Dict[str, List[str]]


# --- MCP Tools ---


@mcp.tool()
def search_artifacts(query: str, limit: int = 10) -> List[ArtifactNode]:
    """
    REQUIRED step for finding any component. Searches the architectural graph.

    You MUST use this tool first when the user asks about a general concept
    (e.g. "payment database", "user service") to get the specific Node ID.
    Do NOT try to guess IDs or file paths.

    Args:
        query: The search string (e.g., "payment", "redis", "user_model").
        limit: Maximum number of results to return (default: 10).

    Returns:
        List[ArtifactNode]: A list of matching nodes with their details.
    """
    try:
        graph = _graph_manager.get_graph()
        # The core graph supports finding nodes by ID pattern
        # Ideally, we'd also search by 'name' attribute or tokens
        matched_ids = graph.find_nodes(query)

        results = []
        for node_id in matched_ids[:limit]:
            node = graph.get_node(node_id)
            if node:
                results.append(
                    ArtifactNode(
                        id=node.id,
                        name=node.name,
                        type=node.type.value,
                        path=node.path,
                        metadata=node.metadata,
                    )
                )
        return results
    except Exception as e:
        logger.error(f"Search failed: {e}")
        return []


@mcp.tool()
def get_neighbors(node_id: str) -> List[NeighborResult]:
    """
    Traverses the graph to find upstream (sources) and downstream (consumers).

    Use this to answer "What uses X?" or "What does X depend on?".
    This is the ONLY way to see cross-domain links (e.g. Terraform -> Python).

    Args:
        node_id: The unique identifier of the artifact (e.g., "env:DB_HOST").

    Returns:
        List[NeighborResult]: A list of connected nodes with relationship details.
    """
    try:
        graph = _graph_manager.get_graph()
        if not graph.has_node(node_id):
            return []

        neighbors = []

        # Downstream (Outgoing edges)
        for edge in graph.get_out_edges(node_id):
            target = graph.get_node(edge.target_id)
            if target:
                neighbors.append(
                    NeighborResult(
                        node=ArtifactNode(
                            id=target.id,
                            name=target.name,
                            type=target.type.value,
                            path=target.path,
                        ),
                        relationship=str(edge.type),
                        direction="downstream",
                    )
                )

        # Upstream (Incoming edges)
        for edge in graph.get_in_edges(node_id):
            source = graph.get_node(edge.source_id)
            if source:
                neighbors.append(
                    NeighborResult(
                        node=ArtifactNode(
                            id=source.id,
                            name=source.name,
                            type=source.type.value,
                            path=source.path,
                        ),
                        relationship=str(edge.type),
                        direction="upstream",
                    )
                )

        return neighbors
    except Exception as e:
        logger.error(f"Get neighbors failed: {e}")
        return []


@mcp.tool()
def get_file_dependencies(path: str) -> Dict[str, List[ArtifactNode]]:
    """
    List all cross-domain dependencies for a specific file.

    Use this tool when the user has a file open and wants to know what
    infrastructure or configuration it interacts with.

    Args:
        path: The file path (relative to repo root, e.g., "src/app.py").

    Returns:
        Dict: Categorized dependencies ("consumes", "provides").
    """
    try:
        graph = _graph_manager.get_graph()
        file_id = f"file://{path}"

        # If strict file node doesn't exist, try to find by path attribute
        if not graph.has_node(file_id):
            # Fallback scan for nodes defined in this file
            file_nodes = [
                n for n in graph.iter_nodes() if n.path and str(n.path).endswith(path)
            ]
            if not file_nodes:
                return {
                    "error": f"File {path} not found in graph. Try running 'jnkn scan'."
                }
            # Use the first matching node, typically the file node itself or a primary definition
            node_ids = [n.id for n in file_nodes]
        else:
            node_ids = [file_id]

        dependencies = {
            "consumes": [],  # Upstream things this file uses (e.g. Env Vars)
            "provides": [],  # Downstream things defined here (e.g. API Routes)
            "internal": [],  # Code-to-code deps
        }

        # Collect edges for all nodes associated with this file
        for nid in node_ids:
            # Outgoing: What does this file/node use?
            for edge in graph.get_out_edges(nid):
                target = graph.get_node(edge.target_id)
                if not target:
                    continue

                art = ArtifactNode(
                    id=target.id, name=target.name, type=target.type.value
                )

                if target.type in (
                    NodeType.ENV_VAR,
                    NodeType.CONFIG_KEY,
                    NodeType.SECRET,
                ):
                    dependencies["consumes"].append(art)
                elif target.type == NodeType.CODE_ENTITY:
                    dependencies["internal"].append(art)
                else:
                    dependencies["provides"].append(art)

        return dependencies

    except Exception as e:
        logger.error(f"Get file dependencies failed: {e}")
        return {"error": str(e)}


@mcp.tool()
def calculate_blast_radius(artifact_id: str) -> BlastRadiusResult:
    """
    Analyzes the full downstream impact of changing an artifact.

    Use this EXACTLY when the user asks "What breaks if I change X?" or "Impact analysis".
    It performs a deep traversal of the dependency graph to find all downstream consumers.

    Args:
        artifact_id: The ID of the artifact to analyze (e.g., "infra:output:db_host").

    Returns:
        BlastRadiusResult: Summary of impacted components broken down by domain.
    """
    try:
        graph = _graph_manager.get_graph()
        analyzer = BlastRadiusAnalyzer(graph)

        # The analyzer returns a dict; we map it to our Pydantic model
        result = analyzer.calculate([artifact_id])

        # Convert breakdown to simple dict[str, List[str]]
        raw_breakdown = result.get("breakdown", {})
        # Ensure values are lists of strings (IDs)
        breakdown = {k: v for k, v in raw_breakdown.items()}

        return BlastRadiusResult(
            source_id=artifact_id,
            impact_count=result.get("total_impacted_count", result.get("count", 0)),
            impacted_nodes=result.get("impacted_artifacts", []),
            breakdown=breakdown,
        )
    except Exception as e:
        logger.error(f"Blast radius calculation failed: {e}")
        # Return empty result rather than crashing
        return BlastRadiusResult(
            source_id=artifact_id, impact_count=0, impacted_nodes=[], breakdown={}
        )


# Entry point for running via `uv run jnkn-ai` or `python -m jnkn_ai.server`
if __name__ == "__main__":
    mcp.run()
