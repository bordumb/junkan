"""Terraform Output Extractor."""

import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class OutputExtractor:
    """Extract Terraform output blocks."""

    name = "terraform_outputs"
    priority = 90

    OUTPUT_PATTERN = re.compile(r'output\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "output" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.OUTPUT_PATTERN.finditer(ctx.text):
            out_name = match.group(1)
            line = ctx.get_line_number(match.start())

            # Use source_repo prefix for multi-repo support
            node_id = f"{ctx.infra_prefix}:output:{out_name}"

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
