import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class ModuleExtractor:
    """Extract module blocks and their input/output relationships."""

    name = "terraform_modules"
    priority = 70

    # Matches module "name" { body }
    # Handles nested braces simply by greedy matching until last brace (simplified for regex)
    # A robust solution needs a brace counter, but regex suffices for well-formatted HCL
    MODULE_PATTERN = re.compile(r'module\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', re.DOTALL)
    SOURCE_PATTERN = re.compile(r'source\s*=\s*"([^"]+)"')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "module" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.MODULE_PATTERN.finditer(ctx.text):
            module_name = match.group(1)
            module_body = match.group(2)
            line = ctx.text[: match.start()].count("\n") + 1

            # Extract source
            source = ""
            if sm := self.SOURCE_PATTERN.search(module_body):
                source = sm.group(1)

            module_id = f"infra:module:{module_name}"

            yield Node(
                id=module_id,
                name=module_name,
                type=NodeType.INFRA_MODULE,
                path=str(ctx.file_path),
                metadata={
                    "terraform_type": "module",
                    "source": source,
                    "line": line,
                },
            )

            # Link file to module
            yield Edge(
                source_id=ctx.file_id,
                target_id=module_id,
                type=RelationshipType.CONTAINS,
            )

            # Extract variable references in module inputs
            # e.g., db_host = aws_db.main.endpoint
            for input_match in re.finditer(r"(\w+)\s*=\s*(\w+\.\w+(?:\.\w+)?)", module_body):
                input_name = input_match.group(1)
                ref_path = input_match.group(2)

                # Create reference edge
                parts = ref_path.split(".")
                if len(parts) >= 2:
                    ref_type, ref_name = parts[0], parts[1]

                    # Normalize ref_type prefixes
                    if ref_type == "var":
                        ref_id = f"infra:var:{ref_name}"
                    elif ref_type == "local":
                        ref_id = f"infra:local:{ref_name}"
                    else:
                        ref_id = f"infra:{ref_type}:{ref_name}"

                    yield Edge(
                        source_id=module_id,
                        target_id=ref_id,
                        type=RelationshipType.DEPENDS_ON,
                        metadata={"input": input_name, "reference": ref_path},
                    )
