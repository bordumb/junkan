import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class DataSourceExtractor:
    """Extract Terraform data blocks."""

    name = "terraform_data_sources"
    priority = 60

    # data "type" "name" { ... }
    DATA_PATTERN = re.compile(r'data\s+"([^"]+)"\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "data" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.DATA_PATTERN.finditer(ctx.text):
            data_type, data_name = match.groups()
            line = ctx.get_line_number(match.start())

            node_id = f"infra:data.{data_type}.{data_name}"

            # Use factory method to ensure path population
            yield ctx.create_infra_node(
                id=node_id,
                name=data_name,
                line=line,
                infra_type=f"data.{data_type}",
                extra_metadata={"terraform_type": data_type, "is_data": True},
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS,
            )
