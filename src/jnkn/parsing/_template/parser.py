"""
Template for creating new language parsers.

To add support for a new language:
1. Copy this template to src/jnkn/parsing/{language}/
2. Rename to parser.py
3. Implement the extractors
4. Register in src/jnkn/parsing/engine.py
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


class TemplateParser(LanguageParser):
    """
    Parser for {LANGUAGE} files.

    Replace this docstring with language-specific documentation.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        """Register all extractors for this language."""
        # TODO: Import and register your extractors
        # from .extractors import (
        #     EnvVarExtractor,
        #     ImportExtractor,
        #     DefinitionExtractor,
        # )
        # self._extractors.register(EnvVarExtractor())
        # self._extractors.register(ImportExtractor())
        pass

    @property
    def name(self) -> str:
        return "template"  # TODO: Change to language name

    @property
    def extensions(self) -> List[str]:
        return [".ext"]  # TODO: Add file extensions

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix.lower() in self.extensions

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
            language=self.name,
        )

        # Create extraction context
        ctx = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            text=text,
            tree=None,  # Set if using tree-sitter
            seen_ids=set(),
        )

        # Run extractors
        yield from self._extractors.extract_all(ctx)


def create_template_parser(context: ParserContext | None = None) -> TemplateParser:
    """Factory function for TemplateParser."""
    return TemplateParser(context)
