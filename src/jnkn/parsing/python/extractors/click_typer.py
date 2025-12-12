import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, ExtractionContext


class ClickTyperExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "click_typer"

    @property
    def priority(self) -> int:
        return 80

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "click" in ctx.text or "typer" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        click_pattern = re.compile(
            r'(?:@click\.option|typer\.Option)\s*\([^)]*envvar\s*=\s*(\[[^\]]+\]|["\'][^"\']+["\'])',
            re.DOTALL,
        )

        for match in click_pattern.finditer(ctx.text):
            envvar_val = match.group(1)
            vars_found = re.findall(r'["\']([^"\']+)["\']', envvar_val)
            line = ctx.text[: match.start()].count("\n") + 1

            for var_name in vars_found:
                if not is_valid_env_var_name(var_name):
                    continue

                if var_name in ctx.seen_ids:
                    continue
                ctx.seen_ids.add(var_name)

                env_id = f"env:{var_name}"

                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "click_typer",
                        "file": str(ctx.file_path),
                        "line": line,
                    },
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": "click_typer", "line": line},
                )
