"""Terraform Resource Extractor."""

import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class ResourceExtractor:
    """Extract Terraform resource blocks."""

    name = "terraform_resources"
    priority = 100

    RESOURCE_PATTERN = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "resource" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.RESOURCE_PATTERN.finditer(ctx.text):
            res_type = match.group(1)
            res_name = match.group(2)
            line = ctx.get_line_number(match.start())

            # Use source_repo prefix for multi-repo support
            node_id = f"{ctx.infra_prefix}:{res_type}.{res_name}"

            yield ctx.create_node(
                id=node_id,
                name=res_name,
                type=NodeType.INFRA_RESOURCE,
                line=line,
                tokens=[res_type, res_name],
                metadata={
                    "terraform_type": "resource",
                    "resource_type": res_type,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS,
            )
