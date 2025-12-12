"""
Java Language Parser.

Handles parsing of Java source files (.java) using regex-based extractors
to find environment variables, imports, and class/method definitions.
"""

from pathlib import Path
from typing import Generator, List, Union

from ...core.types import Edge, Node, NodeType
from ..base import (
    ExtractionContext,
    ExtractorRegistry,
    LanguageParser,
    ParserContext,
)
from .extractors.definitions import JavaDefinitionExtractor
from .extractors.env_vars import JavaEnvVarExtractor
from .extractors.imports import JavaImportExtractor


class JavaParser(LanguageParser):
    """
    Parser for Java source files.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        self._extractors.register(JavaEnvVarExtractor())
        self._extractors.register(JavaImportExtractor())
        self._extractors.register(JavaDefinitionExtractor())

    @property
    def name(self) -> str:
        return "java"

    @property
    def extensions(self) -> List[str]:
        return [".java"]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        return file_path.suffix.lower() == ".java"

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="ignore")

        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="java",
        )

        ctx = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            text=text,
            tree=None,
            seen_ids=set(),
        )

        yield from self._extractors.extract_all(ctx)


def create_java_parser(context: ParserContext | None = None) -> JavaParser:
    return JavaParser(context)
