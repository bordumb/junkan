import re
from pathlib import Path
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class NextJSExtractor:
    """
    Extract Next.js specific patterns.

    Handles:
    - API Routes (pages/api/*, app/api/*)
    - Data fetching methods (getServerSideProps, getStaticProps)
    - next.config.js environment variables and domains
    """

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
            config_id = f"config:nextjs:{ctx.file_path.name}"

            yield Node(
                id=config_id,
                name="next.config",
                type=NodeType.CONFIG_KEY,
                path=str(ctx.file_path),
                metadata={"framework": "nextjs"},
            )

            yield Edge(source_id=ctx.file_id, target_id=config_id, type=RelationshipType.CONTAINS)

            # Extract 'env' block: env: { KEY: "VAL" }
            # Simple regex to catch keys inside the env block
            # This is heuristic and might miss complex dynamic generation
            env_block_match = re.search(r"env\s*:\s*\{([^}]+)\}", ctx.text, re.DOTALL)
            if env_block_match:
                content = env_block_match.group(1)
                # Find keys:  KEY: "value" or KEY,
                keys = re.findall(r"([A-Z_][A-Z0-9_]*)\s*:", content)
                for key in keys:
                    env_id = f"env:{key}"
                    yield Node(
                        id=env_id,
                        name=key,
                        type=NodeType.ENV_VAR,
                        path=str(ctx.file_path),
                        metadata={"source": "next.config.js"},
                    )
                    yield Edge(
                        source_id=config_id,
                        target_id=env_id,
                        type=RelationshipType.PROVIDES,  # Config provides this env var to the app
                        metadata={"context": "build_time_env"},
                    )

            # Extract image domains: images: { domains: ["example.com"] }
            # Useful for detecting external dependencies
            images_match = re.search(
                r"images\s*:\s*\{[^}]*domains\s*:\s*\[([^\]]+)\]", ctx.text, re.DOTALL
            )
            if images_match:
                domains_str = images_match.group(1)
                domains = re.findall(r'["\']([^"\']+)["\']', domains_str)
                for domain in domains:
                    domain_id = f"external:domain:{domain}"
                    yield Node(
                        id=domain_id,
                        name=domain,
                        type=NodeType.DATA_ASSET,  # External resource
                        metadata={"type": "image_domain"},
                    )
                    yield Edge(
                        source_id=config_id,
                        target_id=domain_id,
                        type=RelationshipType.DEPENDS_ON,
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
