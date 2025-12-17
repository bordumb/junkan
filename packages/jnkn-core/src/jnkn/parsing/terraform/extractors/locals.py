"""Terraform Locals Extractor."""

import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class LocalsExtractor:
    """Extract Terraform locals blocks."""

    name = "terraform_locals"
    priority = 80

    LOCALS_BLOCK_PATTERN = re.compile(r"locals\s*\{([^}]+)\}", re.DOTALL)
    LOCAL_ASSIGNMENT_PATTERN = re.compile(r"(\w+)\s*=")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "locals" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for block_match in self.LOCALS_BLOCK_PATTERN.finditer(ctx.text):
            block_content = block_match.group(1)
            block_start_line = ctx.get_line_number(block_match.start())

            for line_match in self.LOCAL_ASSIGNMENT_PATTERN.finditer(block_content):
                local_name = line_match.group(1)

                # Skip if it looks like a nested attribute
                if local_name in ("description", "type", "default", "value", "sensitive"):
                    continue

                local_offset = block_content[: line_match.start()].count("\n")
                line = block_start_line + local_offset

                # Use source_repo prefix for multi-repo support
                node_id = f"{ctx.infra_prefix}:local.{local_name}"

                yield ctx.create_config_node(
                    id=node_id,
                    name=local_name,
                    line=line,
                    config_type="terraform_local",
                    extra_metadata={"terraform_type": "local", "is_local": True},
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=node_id,
                    type=RelationshipType.PROVISIONS,
                )
