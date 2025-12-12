import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class LocalsExtractor:
    """Extract Terraform locals."""

    name = "terraform_locals"
    priority = 50

    # locals { ... }
    # Only finds the block, then uses internal regex to find keys inside
    LOCALS_BLOCK_PATTERN = re.compile(r"locals\s*\{([^}]*)\}", re.DOTALL)

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "locals" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for block_match in self.LOCALS_BLOCK_PATTERN.finditer(ctx.text):
            block_content = block_match.group(1)
            block_start_line = ctx.text[: block_match.start()].count("\n") + 1

            # Extract keys: name = value
            for line_match in re.finditer(
                r"^\s*([a-zA-Z0-9_\-]+)\s*=", block_content, re.MULTILINE
            ):
                local_name = line_match.group(1)

                # Calculate approximate line number
                local_offset = block_content[: line_match.start()].count("\n")
                line = block_start_line + local_offset

                node_id = f"infra:local.{local_name}"

                yield Node(
                    id=node_id,
                    name=local_name,
                    type=NodeType.CONFIG_KEY,
                    path=str(ctx.file_path),
                    metadata={
                        "terraform_type": "local",
                        "is_local": True,
                        "line": line,
                    },
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=node_id,
                    type=RelationshipType.PROVISIONS,
                )
