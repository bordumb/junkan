import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Generator, Optional, Set, Union

from ....core.types import Edge, Node

# Type alias for Tree-sitter tree, using Any as strict typing requires the library
Tree = Any

logger = logging.getLogger(__name__)

class BaseExtractor(ABC):
    """Base class for env var extractors."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this extractor."""
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Higher priority extractors run first (0-100)."""
        pass

    @abstractmethod
    def can_extract(self, text: str) -> bool:
        """Quick check if this extractor is relevant."""
        pass

    @abstractmethod
    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Optional[Tree],  # tree-sitter AST
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract env vars and yield nodes/edges."""
        pass
