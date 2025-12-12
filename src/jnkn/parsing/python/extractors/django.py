import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, ExtractionContext


class DjangoExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "django"

    @property
    def priority(self) -> int:
        return 60

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "environ" in ctx.text or "Env" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        pattern = r'env(?:\.[a-zA-Z_]+)?\s*\(\s*["\']([^"\']+)["\']'
        regex = re.compile(pattern)

        for match in regex.finditer(ctx.text):
            var_name = match.group(1)

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
                    "source": "django_environ",
                    "file": str(ctx.file_path),
                    "line": line,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "django_environ", "line": line},
            )
