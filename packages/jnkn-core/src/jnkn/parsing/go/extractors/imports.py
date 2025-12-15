import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class GoImportExtractor:
    """
    Extract import statements from Go code.
    """

    name = "go_imports"
    priority = 90

    SINGLE_IMPORT = re.compile(r'import\s+(?:[\.\w]+\s+)?"([^"]+)"')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "import" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        imports = set()

        # 1. Single line imports
        for match in self.SINGLE_IMPORT.finditer(ctx.text):
            imports.add(match.group(1))

        # 2. Factored import blocks
        lines = ctx.text.splitlines()
        in_block = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("import ("):
                in_block = True
                continue

            if in_block:
                if stripped.startswith(")"):
                    in_block = False
                    continue

                if '"' in stripped:
                    parts = stripped.split('"')
                    if len(parts) >= 3:
                        pkg_path = parts[1]
                        imports.add(pkg_path)

        for imp in imports:
            parts = imp.split("/")
            domain_in_root = "." in parts[0]
            is_stdlib = not domain_in_root
            pkg_id = f"go:{imp}"

            # Use factory method
            yield ctx.create_code_entity_node(
                name=parts[-1],
                line=1,  # Approx
                entity_type="go_package",
                extra_metadata={
                    "full_path": imp,
                    "is_stdlib": is_stdlib,
                    "virtual": True,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=pkg_id,
                type=RelationshipType.IMPORTS,
            )
