import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class JavaDefinitionExtractor:
    """Extract Class and Interface definitions from Java code."""

    name = "java_definitions"
    priority = 80

    # public class MyClass extends Parent implements Interface {
    # abstract class MyClass ...
    # interface MyInterface ...
    CLASS_DEF = re.compile(
        r"(?:public|protected|private|abstract|final|static|\s)*"
        r"(class|interface|enum|record)\s+"
        r"(\w+)"
    )

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "class" in ctx.text or "interface" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        # We only care about top-level definitions usually, but regex finds all
        # To strictly map file -> class, we look for the public class that matches filename

        filename_no_ext = ctx.file_path.stem

        for match in self.CLASS_DEF.finditer(ctx.text):
            def_type = match.group(1)  # class, interface, etc.
            def_name = match.group(2)

            line = ctx.text[: match.start()].count("\n") + 1
            entity_id = f"entity:{ctx.file_path}:{def_name}"

            yield Node(
                id=entity_id,
                name=def_name,
                type=NodeType.CODE_ENTITY,
                path=str(ctx.file_path),
                language="java",
                metadata={
                    "entity_type": def_type,
                    "line": line,
                    "is_public": def_name == filename_no_ext,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )
