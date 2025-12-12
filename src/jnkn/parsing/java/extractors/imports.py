import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class JavaImportExtractor:
    """Extract import statements from Java code."""

    name = "java_imports"
    priority = 90

    # import com.example.package.Class;
    # import static com.example.package.Class.method;
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

            # Determine if it's likely an external library or internal code
            # Standard Java libraries
            is_stdlib = full_import.startswith(("java.", "javax."))

            # Construct a virtual node for the imported package/class
            # We use 'java:' prefix for Java entities
            pkg_id = f"java:{full_import}"

            # Try to determine simple name (Class name)
            simple_name = full_import.split(".")[-1]

            yield Node(
                id=pkg_id,
                name=simple_name,
                type=NodeType.CODE_ENTITY,
                metadata={
                    "package_type": "java",
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
