import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class GoImportExtractor:
    """
    Extract import statements from Go code.

    Handles:
    - Single line imports: import "fmt"
    - Factored imports: import ( ... )
    - Aliased imports: import log "github.com/sirupsen/logrus"
    - Dot imports: import . "lib/math"
    """

    name = "go_imports"
    priority = 90

    # Single import: import "fmt" or import alias "pkg"
    # Capture group 2 is always the package path
    SINGLE_IMPORT = re.compile(r'import\s+(?:[\.\w]+\s+)?"([^"]+)"')

    # Start of factored import block
    IMPORT_BLOCK_START = re.compile(r"import\s*\(")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "import" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        imports = set()

        # 1. Single line imports
        for match in self.SINGLE_IMPORT.finditer(ctx.text):
            imports.add(match.group(1))

        # 2. Factored import blocks
        # Scan for import ( ... ) blocks
        # This regex-based approach is a simplification; a true parser handles nested parens better
        # but Go imports are simple enough that this usually works.
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

                # Extract package from line: [alias] "package/path"
                if '"' in stripped:
                    parts = stripped.split('"')
                    if len(parts) >= 3:
                        pkg_path = parts[1]
                        imports.add(pkg_path)

        for imp in imports:
            # Determine if stdlib or external
            # Stdlib packages usually don't have a domain part (no ".")
            # Exception: "golang.org/x/..." are effectively extensions
            parts = imp.split("/")
            domain_in_root = "." in parts[0]
            is_stdlib = not domain_in_root

            # Construct a node for the package
            # We use 'go:' prefix for Go packages
            pkg_id = f"go:{imp}"

            yield Node(
                id=pkg_id,
                name=parts[-1],  # package name
                type=NodeType.CODE_ENTITY,
                metadata={
                    "package_type": "go_package",
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
