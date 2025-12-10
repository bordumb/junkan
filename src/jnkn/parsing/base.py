"""
Base Parser Infrastructure.
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Union, Set

from ..core.interfaces import IParser
from ..core.types import Node, Edge


class ParserContext:
    """Context passed to parsers (e.g., root directory)."""
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir


class BaseParser(IParser, ABC):
    """
    Abstract Base Class for all language parsers.
    Enforces strict typing of return values.
    """

    def __init__(self, context: ParserContext):
        self.context = context

    @abstractmethod
    def can_parse(self, file_path: Path) -> bool:
        """
        Determine if this parser supports the given file.
        """
        pass

    @abstractmethod
    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        """
        Parse the file content.
        
        Must return a list containing strictly:
        - jnkn.core.types.Node objects
        - jnkn.core.types.Edge objects
        """
        pass
    
    def _relativize(self, path: Path) -> str:
        """Helper to get path relative to project root."""
        try:
            return str(path.relative_to(self.context.root_dir))
        except ValueError:
            return str(path)


class CompositeParser(BaseParser):
    """
    Parser that delegates to multiple sub-parsers.
    Used to handle directories or multiple file types.
    """
    def __init__(self, context: ParserContext, parsers: List[BaseParser]):
        super().__init__(context)
        self.parsers = parsers

    def can_parse(self, file_path: Path) -> bool:
        return any(p.can_parse(file_path) for p in self.parsers)

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results = []
        for parser in self.parsers:
            if parser.can_parse(file_path):
                results.extend(parser.parse(file_path, content))
        return results