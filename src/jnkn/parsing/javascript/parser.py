"""
JavaScript/TypeScript Language Parser.

Handles parsing of JS, TS, JSX, TSX files and package.json.
Supports multiple frameworks (Next.js, Vite, React) via specialized extractors.
"""

import logging
from pathlib import Path
from typing import Generator, List, Union

from ...core.types import Edge, Node, NodeType
from ..base import (
    ExtractionContext,
    ExtractorRegistry,
    LanguageParser,
    ParserCapability,
    ParserContext,
)
from .extractors import JAVASCRIPT_EXTRACTORS

logger = logging.getLogger(__name__)

try:
    from tree_sitter_languages import get_language, get_parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


class JavaScriptParser(LanguageParser):
    """
    Parser for JavaScript ecosystem files.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        for extractor in JAVASCRIPT_EXTRACTORS:
            self._extractors.register(extractor)

        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None

    @property
    def name(self) -> str:
        return "javascript"

    @property
    def extensions(self) -> List[str]:
        return [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.IMPORTS,
            ParserCapability.ENV_VARS,
            ParserCapability.DEFINITIONS,
        ]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        if file_path.name == "package.json":
            return True
        return file_path.suffix.lower() in self.extensions

    def _init_tree_sitter(self, file_path: Path) -> bool:
        """Initialize tree-sitter with the correct grammar (js or ts)."""
        if not TREE_SITTER_AVAILABLE:
            return False

        ext = file_path.suffix.lower()
        lang_name = "typescript" if ext in (".ts", ".tsx") else "javascript"

        try:
            self._ts_parser = get_parser(lang_name)
            self._ts_language = get_language(lang_name)
            return True
        except Exception as e:
            self._logger.warning(f"Failed to initialize tree-sitter for {lang_name}: {e}")
            return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        from ...core.types import ScanMetadata

        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            return

        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception:
            file_hash = ""

        ext = file_path.suffix.lower()
        lang = "typescript" if ext in (".ts", ".tsx") else "javascript"
        if file_path.name == "package.json":
            lang = "json"

        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language=lang,
            file_hash=file_hash,
        )

        tree = None
        if self._init_tree_sitter(file_path):
            try:
                tree = self._ts_parser.parse(content)
            except Exception:
                pass

        ctx = ExtractionContext(
            file_path=file_path, file_id=file_id, text=text, tree=tree, seen_ids=set()
        )

        yield from self._extractors.extract_all(ctx)


def create_javascript_parser(context: ParserContext | None = None) -> JavaScriptParser:
    return JavaScriptParser(context)
