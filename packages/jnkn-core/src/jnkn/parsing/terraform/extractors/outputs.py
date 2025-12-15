import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
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
            line = ctx.get_line_number(match.start())

            node_id = f"infra:output:{out_name}"

            # Use factory method to ensure path population
            yield ctx.create_config_node(
                id=node_id,
                name=out_name,
                line=line,
                config_type="terraform_output",
                extra_metadata={"terraform_type": "output"},
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS,
            )
