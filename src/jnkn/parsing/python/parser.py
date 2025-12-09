from pathlib import Path
from typing import Generator, List, Optional, Set, Union
import logging

from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)
from ...core.types import Node, Edge, NodeType, RelationshipType, ScanMetadata
from .extractors import get_extractors

logger = logging.getLogger(__name__)

# Check if tree-sitter is available
try:
    from tree_sitter_languages import get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.debug("tree-sitter not available")

class PythonParser(LanguageParser):
    """
    Orchestrating Python Parser.
    
    Delegates actual extraction to specialized Extractor classes.
    """
    
    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._extractors = get_extractors()
        self._tree_sitter_initialized = False
        self._ts_parser = None

    @property
    def name(self) -> str:
        return "python"
    
    @property
    def extensions(self) -> List[str]:
        return [".py", ".pyi"]
    
    @property
    def description(self) -> str:
        return "Python parser with pluggable extractors"
    
    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.IMPORTS,
            ParserCapability.ENV_VARS,
            ParserCapability.DEFINITIONS,
            ParserCapability.CONFIGS,
        ]

    def _init_tree_sitter(self) -> bool:
        """Initialize tree-sitter parser lazily."""
        if self._tree_sitter_initialized:
            return self._ts_parser is not None
        
        self._tree_sitter_initialized = True
        
        if not TREE_SITTER_AVAILABLE:
            return False
        
        try:
            self._ts_parser = get_parser("python")
            return True
        except Exception as e:
            self._logger.warning(f"Failed to initialize tree-sitter: {e}")
            return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a Python file and yield nodes and edges.
        """
        # Create file node
        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception:
            file_hash = ""
        
        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="python",
            file_hash=file_hash,
        )
        
        # Decode content
        try:
            text = content.decode(self._context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                self._logger.error(f"Failed to decode {file_path}: {e}")
                return

        # Prepare AST if possible
        tree = None
        if self._init_tree_sitter():
            tree = self._ts_parser.parse(content)

        # Track what we've yielded to avoid duplicates (Precision fix)
        # We track (id, type) for nodes to ensure we only emit a node once per file.
        # Edges can be multiple if they are distinct, but usually one edge per relationship is preferred.
        yielded_node_ids: Set[str] = set()
        
        # This set is passed to extractors to coordinate logic if needed
        seen_vars: Set[str] = set()
        
        for extractor in self._extractors:
            if extractor.can_extract(text):
                try:
                    for item in extractor.extract(file_path, file_id, tree, text, seen_vars):
                        
                        # Handle Node Deduplication
                        if isinstance(item, Node):
                            if item.id in yielded_node_ids:
                                continue
                            yielded_node_ids.add(item.id)
                            
                            # Update seen_vars for extractor coordination
                            if item.type == NodeType.ENV_VAR:
                                seen_vars.add(item.name)
                        
                        # Always yield edges (they represent specific usages on lines)
                        # OR: You could dedup edges too if you only want 1 dependency per file
                        # For now, yielding all edges is better for "where is this used?" queries,
                        # but nodes must be unique.
                        if isinstance(item, Edge):
                            yield item
                        else:
                            yield item

                except Exception as e:
                    self._logger.error(f"Extractor {extractor.name} failed on {file_path}: {e}")

def create_python_parser(context: Optional[ParserContext] = None) -> PythonParser:
    """Factory function to create a Python parser."""
    return PythonParser(context)