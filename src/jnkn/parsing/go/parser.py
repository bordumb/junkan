"""
Standardized Go Parser.

Provides parsing for Go source files (.go), extracting:
- Environment variable usage (os.Getenv, os.LookupEnv, viper)
- Import declarations (standard library and external packages)
- Function and type definitions (structs, interfaces)

This parser supports standard Go idioms as well as common configuration
patterns used in cloud-native Go applications.
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
from .extractors.definitions import GoDefinitionExtractor
from .extractors.env_vars import GoEnvVarExtractor
from .extractors.imports import GoImportExtractor


class GoParser(LanguageParser):
    """
    Parser for Go source files (.go).
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        """Register all extractors for Go."""
        self._extractors.register(GoEnvVarExtractor())
        self._extractors.register(GoImportExtractor())
        self._extractors.register(GoDefinitionExtractor())

    @property
    def name(self) -> str:
        return "go"

    @property
    def extensions(self) -> List[str]:
        return [".go"]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        return file_path.suffix.lower() == ".go"

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
            language="go",
        )

        # Create extraction context
        ctx = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            text=text,
            tree=None,
            seen_ids=set(),
        )

        # Run extractors
        yield from self._extractors.extract_all(ctx)


def create_go_parser(context: ParserContext | None = None) -> GoParser:
    """Factory function for GoParser."""
    return GoParser(context)
