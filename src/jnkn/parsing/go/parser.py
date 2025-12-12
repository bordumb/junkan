"""
Go Language Parser.

Handles parsing of Go source files (.go) using regex-based extractors
to find environment variables, imports, and definitions.
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
    Parser for Go source files.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
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
            language="go",
        )

        ctx = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            text=text,
            tree=None,
            seen_ids=set(),
        )

        yield from self._extractors.extract_all(ctx)


def create_go_parser(context: ParserContext | None = None) -> GoParser:
    return GoParser(context)
