"""
Standardized Python Parser.
"""

from pathlib import Path
from typing import Any, List, Set, Union

# Type alias for Tree-sitter tree, using Any as strict typing requires the library
Tree = Any

try:
    from tree_sitter_languages import get_language, get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ...core.types import Edge, Node, NodeType
from ..base import LanguageParser, ParserContext
from .extractors import get_extractors


class PythonParser(LanguageParser):
    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = get_extractors()
        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None

    @property
    def name(self) -> str:
        return "python"

    @property
    def extensions(self) -> List[str]:
        return [".py"]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def _init_tree_sitter(self) -> bool:
        """Initialize tree-sitter parser lazily."""
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

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results: List[Union[Node, Edge]] = []
        
        try:
            # Decode content
            text = content.decode(self.context.encoding)
        except Exception:
            try:
                text = content.decode("latin-1")
            except Exception:
                return []

        rel_path = self._relativize(file_path)
        file_id = f"file://{rel_path}"
        
        # 1. Create the File Node
        file_node = Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=rel_path,
            metadata={"language": "python"}
        )
        results.append(file_node)

        # 2. Parse with tree-sitter if available (for better AST analysis)
        tree = None
        if self._init_tree_sitter():
            try:
                tree = self._ts_parser.parse(content)
            except Exception:
                pass

        # 3. Run all registered extractors
        seen_vars: Set[str] = set()
        
        for extractor in self._extractors:
            if not extractor.can_extract(text):
                continue
                
            try:
                for item in extractor.extract(file_path, file_id, tree, text, seen_vars):
                    results.append(item)
                    
                    # Track seen env vars to prevent duplicates across extractors
                    # (Higher priority extractors take precedence)
                    if isinstance(item, Node) and item.type == NodeType.ENV_VAR:
                        seen_vars.add(item.name)
            except Exception as e:
                self._logger.debug(f"Extractor {extractor.name} failed on {file_path}: {e}")

        return results


def create_python_parser(context: ParserContext | None = None) -> PythonParser:
    """Factory function to create a Python parser."""
    return PythonParser(context)
