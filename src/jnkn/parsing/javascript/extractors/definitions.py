"""
Definition Extractor for JavaScript/TypeScript.
"""

import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class DefinitionExtractor:
    """
    Extract function and class definitions.

    Handles:
    - function Name() {}
    - class Name {}
    - const Name = () => {} (arrow functions - simplified)
    """

    name = "js_definitions"
    priority = 80

    # Standard function/class definitions
    DEF_PATTERN = re.compile(
        r"^(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)", re.MULTILINE
    )

    # React component pattern (simplified PascalCase const assignment)
    REACT_COMPONENT = re.compile(r"const\s+([A-Z]\w+)\s*=\s*(?:\([^)]*\)|props)\s*=>", re.MULTILINE)

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "function" in ctx.text or "class" in ctx.text or "=>" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        seen_defs = set()

        # 1. Standard Definitions
        for match in self.DEF_PATTERN.finditer(ctx.text):
            def_name = match.group(1)
            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)

            yield from self._create_entity(ctx, def_name, match.start(), "standard")

        # 2. React Components / Arrow Functions
        for match in self.REACT_COMPONENT.finditer(ctx.text):
            def_name = match.group(1)
            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)

            yield from self._create_entity(ctx, def_name, match.start(), "component")

    def _create_entity(self, ctx: ExtractionContext, name: str, pos: int, kind: str):
        line = ctx.text[:pos].count("\n") + 1
        entity_id = f"entity:{ctx.file_path}:{name}"

        yield Node(
            id=entity_id,
            name=name,
            type=NodeType.CODE_ENTITY,
            path=str(ctx.file_path),
            language="javascript",
            metadata={"entity_type": kind, "line": line},
        )

        yield Edge(source_id=ctx.file_id, target_id=entity_id, type=RelationshipType.CONTAINS)
