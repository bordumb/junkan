import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class ResourceExtractor:
    """Extract Terraform resource blocks."""

    name = "terraform_resources"
    priority = 100

    # resource "type" "name" { ... }
    RESOURCE_PATTERN = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "resource" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.RESOURCE_PATTERN.finditer(ctx.text):
            res_type, res_name = match.groups()
            line = ctx.text[: match.start()].count("\n") + 1

            node_id = f"infra:{res_type}.{res_name}"

            yield Node(
                id=node_id,
                name=res_name,
                type=NodeType.INFRA_RESOURCE,
                path=str(ctx.file_path),
                metadata={
                    "terraform_type": res_type,
                    "line": line,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS,
            )
