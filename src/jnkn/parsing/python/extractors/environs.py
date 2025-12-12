import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, ExtractionContext


class EnvironsExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "environs"

    @property
    def priority(self) -> int:
        return 40

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "env" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        pattern = r'env\.(str|int|bool|float|list|dict|json|url|path|db|cache|email_url|search_url)\s*\(\s*["\']([^"\']+)["\']'
        regex = re.compile(pattern)

        for match in regex.finditer(ctx.text):
            var_name = match.group(2)

            if not is_valid_env_var_name(var_name):
                continue

            if var_name in ctx.seen_ids:
                continue
            ctx.seen_ids.add(var_name)

            line = ctx.text[: match.start()].count("\n") + 1
            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "environs",
                    "file": str(ctx.file_path),
                    "line": line,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "environs", "line": line},
            )
