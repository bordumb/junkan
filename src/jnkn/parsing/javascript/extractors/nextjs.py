import re
from pathlib import Path
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class NextJSExtractor:
    """Extract Next.js specific patterns."""

    name = "nextjs"
    priority = 70

    # Patterns for Next.js data fetching methods
    GET_SERVER_PROPS = re.compile(
        r"export\s+(?:async\s+)?function\s+getServerSideProps", re.MULTILINE
    )
    GET_STATIC_PROPS = re.compile(r"export\s+(?:async\s+)?function\s+getStaticProps", re.MULTILINE)
    API_HANDLER = re.compile(r"export\s+default\s+(?:async\s+)?function\s+handler", re.MULTILINE)

    def can_extract(self, ctx: ExtractionContext) -> bool:
        # Check if this looks like a Next.js file based on path
        path_str = str(ctx.file_path)
        return "pages/" in path_str or "app/" in path_str or "next.config" in path_str

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        path_str = str(ctx.file_path)

        # API Routes detection
        # FIX: Removed leading slash to handle relative paths
        if "pages/api/" in path_str or "app/api/" in path_str:
            route_path = self._path_to_route(ctx.file_path)

            api_node_id = f"api:{route_path}"

            yield Node(
                id=api_node_id,
                name=route_path,
                type=NodeType.CODE_ENTITY,
                path=str(ctx.file_path),
                metadata={
                    "framework": "nextjs",
                    "type": "api_route",
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=api_node_id,
                type=RelationshipType.CONTAINS,
            )

        # Server-side data fetching functions
        if self.GET_SERVER_PROPS.search(ctx.text):
            func_id = f"entity:{ctx.file_path}:getServerSideProps"
            yield Node(
                id=func_id,
                name="getServerSideProps",
                type=NodeType.CODE_ENTITY,
                path=str(ctx.file_path),
                metadata={
                    "framework": "nextjs",
                    "type": "server_function",
                    "runs_on": "server",
                },
            )
            yield Edge(source_id=ctx.file_id, target_id=func_id, type=RelationshipType.CONTAINS)

        # Config file parsing
        if "next.config" in path_str:
            # Placeholder for config extraction logic
            yield Node(
                id=f"config:nextjs:{ctx.file_path.name}",
                name="next.config",
                type=NodeType.CONFIG_KEY,
                path=str(ctx.file_path),
            )

    def _path_to_route(self, file_path: Path) -> str:
        """Convert file path to API route string."""
        path_str = str(file_path)

        # pages/api/users/[id].ts -> /api/users/[id]
        if "pages/api/" in path_str:
            route = path_str.split("pages/api/")[1]
        elif "app/api/" in path_str:
            route = path_str.split("app/api/")[1]
        else:
            return str(file_path)

        # Remove extension
        route = re.sub(r"\.(ts|tsx|js|jsx)$", "", route)
        # Handle index files
        if route.endswith("/index"):
            route = route[:-6]
        elif route == "index":
            route = ""

        return f"/api/{route}"
