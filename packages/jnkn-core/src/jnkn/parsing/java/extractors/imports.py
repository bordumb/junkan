import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class JavaImportExtractor:
    """Extract import statements from Java code."""

    name = "java_imports"
    priority = 90

    IMPORT_PATTERN = re.compile(r"import\s+(?:static\s+)?([\w\.]+);")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "import" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        seen_imports = set()

        for match in self.IMPORT_PATTERN.finditer(ctx.text):
            full_import = match.group(1)

            if full_import in seen_imports:
                continue
            seen_imports.add(full_import)

            is_stdlib = full_import.startswith(("java.", "javax."))
            pkg_id = f"java:{full_import}"
            simple_name = full_import.split(".")[-1]
            line = ctx.get_line_number(match.start())

            # Use factory method
            yield ctx.create_code_entity_node(
                name=simple_name,
                line=line,
                entity_type="java_package",
                extra_metadata={
                    "full_path": full_import,
                    "is_stdlib": is_stdlib,
                    "virtual": True,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=pkg_id,
                type=RelationshipType.IMPORTS,
            )
