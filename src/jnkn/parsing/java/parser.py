"""
Standardized Java Parser.

Provides comprehensive parsing for Java source files, focusing on:
- Environment variable detection (System.getenv, Spring @Value)
- Property retrieval (System.getProperty, Spring Environment)
- Import statement extraction
- Class and method definition extraction

This parser is designed to support enterprise Java applications, including
Spring Boot and standard Java SE patterns.
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
    Parser for Java source files (.java).
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        """Register all extractors for Java."""
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
        # Decode content
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            text = content.decode("latin-1", errors="ignore")

        # Create file node
        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="java",
        )

        # Create extraction context
        # Note: tree-sitter integration can be added here in the future
        # by passing the parsed tree to the context.
        ctx = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            text=text,
            tree=None,
            seen_ids=set(),
        )

        # Run extractors
        yield from self._extractors.extract_all(ctx)


def create_java_parser(context: ParserContext | None = None) -> JavaParser:
    """Factory function for JavaParser."""
    return JavaParser(context)
