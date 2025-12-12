"""
Python Language Parser.

Handles parsing of Python source code using Tree-sitter (if available)
and Regex-based extractors for robustness.
"""

from pathlib import Path
from typing import Any, Generator, List, Union

# Type alias for Tree-sitter tree
Tree = Any

try:
    from tree_sitter_languages import get_language, get_parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...core.types import Edge, Node, NodeType
from ..base import (
    ExtractionContext,
    ExtractorRegistry,
    LanguageParser,
    ParserContext,
)
from .extractors import get_extractors


class PythonParser(LanguageParser):
    """
    Parser for Python (.py) files.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        for extractor in get_extractors():
            self._extractors.register(extractor)

        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None

    @property
    def name(self) -> str:
        return "python"

    @property
    def extensions(self) -> List[str]:
        return [".py"]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        return file_path.suffix == ".py"

    def _init_tree_sitter(self) -> bool:
        """Initialize tree-sitter resources lazily."""
        if not TREE_SITTER_AVAILABLE:
            return False

        if self._tree_sitter_initialized:
            return True

        try:
            self._ts_parser = get_parser("python")
            self._ts_language = get_language("python")
            self._tree_sitter_initialized = True
            return True
        except Exception as e:
            self._logger.warning(f"Failed to initialize tree-sitter: {e}")
            return False

    def parse(self, file_path: Path, content: bytes) -> Generator[Union[Node, Edge], None, None]:
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception:
                return

        rel_path = self._relativize(file_path)
        file_id = f"file://{rel_path}"

        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=rel_path,
            metadata={"language": "python"},
        )

        tree = None
        if self._init_tree_sitter():
            try:
                tree = self._ts_parser.parse(content)
            except Exception:
                pass

        ctx = ExtractionContext(
            file_path=file_path, file_id=file_id, text=text, tree=tree, seen_ids=set()
        )

        yield from self._extractors.extract_all(ctx)


def create_python_parser(context: ParserContext | None = None) -> PythonParser:
    return PythonParser(context)
