import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class ModuleExtractor:
    """Extract module blocks and their input/output relationships."""

    name = "terraform_modules"
    priority = 70

    MODULE_PATTERN = re.compile(r'module\s+"([^"]+)"\s*\{([^}]*(?:\{[^}]*\}[^}]*)*)\}', re.DOTALL)
    SOURCE_PATTERN = re.compile(r'source\s*=\s*"([^"]+)"')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "module" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.MODULE_PATTERN.finditer(ctx.text):
            module_name = match.group(1)
            module_body = match.group(2)
            line = ctx.get_line_number(match.start())

            # Extract source
            source = ""
            if sm := self.SOURCE_PATTERN.search(module_body):
                source = sm.group(1)

            module_id = f"infra:module:{module_name}"

            # Use factory logic. Since INFRA_MODULE isn't a factory helper, use create_node.
            yield ctx.create_node(
                id=module_id,
                name=module_name,
                type=NodeType.INFRA_MODULE,
                line=line,
                metadata={
                    "terraform_type": "module",
                    "source": source,
                },
            )

            # Link file to module
            yield Edge(
                source_id=ctx.file_id,
                target_id=module_id,
                type=RelationshipType.CONTAINS,
            )

            # Extract variable references in module inputs
            for input_match in re.finditer(r"(\w+)\s*=\s*(\w+\.\w+(?:\.\w+)?)", module_body):
                input_name = input_match.group(1)
                ref_path = input_match.group(2)

                parts = ref_path.split(".")
                if len(parts) >= 2:
                    ref_type, ref_name = parts[0], parts[1]

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
