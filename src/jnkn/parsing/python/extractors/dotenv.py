import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, ExtractionContext


class DotenvExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "dotenv"

    @property
    def priority(self) -> int:
        return 70

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "dotenv" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        # 1. Inline usage
        inline_pattern = r'dotenv_values\s*\([^)]*\)\s*\[\s*["\']([^"\']+)["\']'
        for match in re.finditer(inline_pattern, ctx.text):
            yield from self._yield_match(match, 1, ctx, "dotenv_values")

        # 2. Assignment tracking
        assignment_pattern = r"(\w+)\s*=\s*dotenv_values\s*\("
        config_vars = set()
        for match in re.finditer(assignment_pattern, ctx.text):
            config_vars.add(match.group(1))

        if config_vars:
            vars_regex = "|".join(re.escape(v) for v in config_vars)

            dict_access_pattern = rf'(?:{vars_regex})\s*\[\s*["\']([^"\']+)["\']'
            for match in re.finditer(dict_access_pattern, ctx.text):
                yield from self._yield_match(match, 1, ctx, "dotenv_values")

            get_access_pattern = rf'(?:{vars_regex})\.get\s*\(\s*["\']([^"\']+)["\']'
            for match in re.finditer(get_access_pattern, ctx.text):
                yield from self._yield_match(match, 1, ctx, "dotenv_values")

    def _yield_match(self, match, group_idx, ctx: ExtractionContext, pattern_name):
        var_name = match.group(group_idx)

        if not is_valid_env_var_name(var_name):
            return

        if var_name in ctx.seen_ids:
            return
        ctx.seen_ids.add(var_name)

        line = ctx.text[: match.start()].count("\n") + 1
        env_id = f"env:{var_name}"

        yield Node(
            id=env_id,
            name=var_name,
            type=NodeType.ENV_VAR,
            metadata={
                "source": "dotenv",
                "file": str(ctx.file_path),
                "line": line,
            },
        )

        yield Edge(
            source_id=ctx.file_id,
            target_id=env_id,
            type=RelationshipType.READS,
            metadata={"pattern": pattern_name, "line": line},
        )
