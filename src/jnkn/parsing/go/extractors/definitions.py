import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class GoDefinitionExtractor:
    """
    Extract function and type definitions from Go code.

    Handles:
    - Functions: func MyFunc(...)
    - Methods: func (r *Receiver) Method(...)
    - Types: type MyStruct struct { ... }
    - Interfaces: type MyInterface interface { ... }
    """

    name = "go_definitions"
    priority = 80

    # func FunctionName(...)
    FUNC_DEF = re.compile(r"^func\s+(\w+)\s*\(", re.MULTILINE)

    # func (recv) MethodName(...)
    METHOD_DEF = re.compile(r"^func\s+\([^)]+\)\s+(\w+)\s*\(", re.MULTILINE)

    # type TypeName struct/interface
    TYPE_DEF = re.compile(r"^type\s+(\w+)\s+(struct|interface)", re.MULTILINE)

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "func" in ctx.text or "type" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        filename_no_ext = ctx.file_path.stem

        # 1. Functions
        for match in self.FUNC_DEF.finditer(ctx.text):
            func_name = match.group(1)
            line = ctx.text[: match.start()].count("\n") + 1

            entity_id = f"entity:{ctx.file_path}:{func_name}"
            is_exported = func_name[0].isupper()

            yield Node(
                id=entity_id,
                name=func_name,
                type=NodeType.CODE_ENTITY,
                path=str(ctx.file_path),
                language="go",
                metadata={"entity_type": "function", "line": line, "is_exported": is_exported},
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )

        # 2. Methods
        for match in self.METHOD_DEF.finditer(ctx.text):
            method_name = match.group(1)
            line = ctx.text[: match.start()].count("\n") + 1

            entity_id = f"entity:{ctx.file_path}:{method_name}"
            is_exported = method_name[0].isupper()

            yield Node(
                id=entity_id,
                name=method_name,
                type=NodeType.CODE_ENTITY,
                path=str(ctx.file_path),
                language="go",
                metadata={"entity_type": "method", "line": line, "is_exported": is_exported},
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )

        # 3. Types (Structs/Interfaces)
        for match in self.TYPE_DEF.finditer(ctx.text):
            type_name = match.group(1)
            kind = match.group(2)  # struct or interface
            line = ctx.text[: match.start()].count("\n") + 1

            entity_id = f"entity:{ctx.file_path}:{type_name}"
            is_exported = type_name[0].isupper()

            yield Node(
                id=entity_id,
                name=type_name,
                type=NodeType.CODE_ENTITY,
                path=str(ctx.file_path),
                language="go",
                metadata={"entity_type": kind, "line": line, "is_exported": is_exported},
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )
