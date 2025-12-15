import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class LocalsExtractor:
    """Extract Terraform locals."""

    name = "terraform_locals"
    priority = 50

    # locals { ... }
    LOCALS_BLOCK_PATTERN = re.compile(r"locals\s*\{([^}]*)\}", re.DOTALL)

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "locals" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for block_match in self.LOCALS_BLOCK_PATTERN.finditer(ctx.text):
            block_content = block_match.group(1)
            block_start_line = ctx.get_line_number(block_match.start())

            # Extract keys: name = value
            for line_match in re.finditer(
                r"^\s*([a-zA-Z0-9_\-]+)\s*=", block_content, re.MULTILINE
            ):
                local_name = line_match.group(1)

                # Calculate approximate line number
                local_offset = block_content[: line_match.start()].count("\n")
                line = block_start_line + local_offset

                node_id = f"infra:local.{local_name}"

                # Use factory method to ensure path population
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
