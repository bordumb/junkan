import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class OutputExtractor:
    """Extract Terraform output blocks."""

    name = "terraform_outputs"
    priority = 90

    # output "name" { ... }
    OUTPUT_PATTERN = re.compile(r'output\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "output" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.OUTPUT_PATTERN.finditer(ctx.text):
            out_name = match.group(1)
            line = ctx.text[: match.start()].count("\n") + 1

            node_id = f"infra:output:{out_name}"

            yield Node(
                id=node_id,
                name=out_name,
                type=NodeType.CONFIG_KEY,
                path=str(ctx.file_path),
                metadata={
                    "terraform_type": "output",
                    "line": line,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS,
            )
