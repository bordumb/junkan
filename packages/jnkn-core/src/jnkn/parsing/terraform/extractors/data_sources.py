"""Terraform Data Source Extractor."""

import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class DataSourceExtractor:
    """Extract Terraform data blocks."""

    name = "terraform_data_sources"
    priority = 95

    DATA_PATTERN = re.compile(r'data\s+"([^"]+)"\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "data" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.DATA_PATTERN.finditer(ctx.text):
            data_type = match.group(1)
            data_name = match.group(2)
            line = ctx.get_line_number(match.start())

            # Use source_repo prefix for multi-repo support
            node_id = f"{ctx.infra_prefix}:data.{data_type}.{data_name}"

            yield ctx.create_node(
                id=node_id,
                name=data_name,
                type=NodeType.DATA_ASSET,
                line=line,
                tokens=[data_type, data_name],
                metadata={
                    "terraform_type": "data",
                    "data_type": data_type,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=node_id,
                type=RelationshipType.READS,
            )
