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

            # Use create_node directly instead of create_code_entity_node
            # This allows us to use the custom 'api:...' ID format required by tests
            # while still getting the 'path' field populated automatically.
            yield ctx.create_node(
                id=api_node_id,
                name=route_path,
                type=NodeType.CODE_ENTITY,
                line=1,
                metadata={
                    "framework": "nextjs",
                    "type": "api_route",
                },
            )

            yield ctx.create_contains_edge(target_id=api_node_id)

        # Server-side data fetching functions
        if self.GET_SERVER_PROPS.search(ctx.text):
            # For standard functions, create_code_entity_node is fine
            yield ctx.create_code_entity_node(
                name="getServerSideProps",
                line=1,
                entity_type="server_function",
                extra_metadata={"framework": "nextjs", "runs_on": "server"},
            )

            func_id = f"entity:{ctx.file_path}:getServerSideProps"
            yield ctx.create_contains_edge(target_id=func_id)

        # Config file parsing
        if "next.config" in path_str:
            config_id = f"config:nextjs:{ctx.file_path.name}"

            yield ctx.create_config_node(
                id=config_id,
                name="next.config",
                config_type="nextjs_config",
                extra_metadata={"framework": "nextjs"},
            )

            yield ctx.create_contains_edge(target_id=config_id)

            # Extract 'env' block: env: { KEY: "VAL" }
            env_block_match = re.search(r"env\s*:\s*\{([^}]+)\}", ctx.text, re.DOTALL)
            if env_block_match:
                content = env_block_match.group(1)
                keys = re.findall(r"([A-Z_][A-Z0-9_]*)\s*:", content)
                for key in keys:
                    # env var node creation handles the ID internally (env:NAME)
                    yield ctx.create_env_var_node(
                        name=key,
                        line=1,
                        source="next.config.js",
                    )

                    yield Edge(
                        source_id=config_id,
                        target_id=f"env:{key}",
                        type=RelationshipType.PROVIDES,
                        metadata={"context": "build_time_env"},
                    )

            # Extract image domains
            images_match = re.search(
                r"images\s*:\s*\{[^}]*domains\s*:\s*\[([^\]]+)\]", ctx.text, re.DOTALL
            )
            if images_match:
                domains_str = images_match.group(1)
                domains = re.findall(r'["\']([^"\']+)["\']', domains_str)
                for domain in domains:
                    domain_id = f"external:domain:{domain}"

                    yield ctx.create_node(
                        id=domain_id,
                        name=domain,
                        type=NodeType.DATA_ASSET,
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
