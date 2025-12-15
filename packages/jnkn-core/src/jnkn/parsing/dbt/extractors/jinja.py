import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import BaseExtractor, ExtractionContext


class JinjaExtractor(BaseExtractor):
    """
    Extracts environment variables and configuration variables from dbt Jinja templates.

    Detects:
    - env_var('KEY') -> Links to System Environment
    - var('key') -> Links to dbt Project Variables
    """

    name = "dbt_jinja"
    priority = 95

    # Match env_var('KEY', default) anywhere
    ENV_VAR_PATTERN = re.compile(r"env_var\s*\(\s*['\"]([^'\"]+)['\"](?:,\s*[^)]*)?\s*\)")

    # Match var('key', default) anywhere
    # Added negative lookbehind (?<![a-zA-Z0-9_]) to avoid matching 'env_var' as 'var'
    VAR_PATTERN = re.compile(r"(?<![a-zA-Z0-9_])var\s*\(\s*['\"]([^'\"]+)['\"](?:,\s*[^)]*)?\s*\)")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        """Check if file contains Jinja markers."""
        # Simple heuristic: must look like a template
        return "{{" in ctx.text or "{%" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        source_node_id = ctx.file_id

        # 1. Environment Variables
        seen_envs = set()
        for match in self.ENV_VAR_PATTERN.finditer(ctx.text):
            env_name = match.group(1)

            if env_name in seen_envs:
                continue
            seen_envs.add(env_name)

            env_id = f"env:{env_name}"
            line = ctx.text[: match.start()].count("\n") + 1

            yield Node(
                id=env_id,
                name=env_name,
                type=NodeType.ENV_VAR,
                metadata={"source": "dbt_jinja", "file": str(ctx.file_path), "line": line},
            )

            yield Edge(
                source_id=source_node_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "env_var", "line": line},
            )

        # 2. dbt Variables
        seen_vars = set()
        for match in self.VAR_PATTERN.finditer(ctx.text):
            var_name = match.group(1)

            if var_name in seen_vars:
                continue
            seen_vars.add(var_name)

            var_id = f"config:dbt:{var_name}"
            line = ctx.text[: match.start()].count("\n") + 1

            yield Node(
                id=var_id,
                name=var_name,
                type=NodeType.CONFIG_KEY,
                metadata={"source": "dbt_var", "file": str(ctx.file_path), "line": line},
            )

            yield Edge(
                source_id=source_node_id,
                target_id=var_id,
                type=RelationshipType.READS,
                metadata={"pattern": "var", "line": line},
            )
