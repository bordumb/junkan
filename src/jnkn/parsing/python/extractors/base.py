import logging
from abc import ABC, abstractmethod
from typing import Generator, Union

from ....core.types import Edge, Node
from ...base import ExtractionContext

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
    def can_extract(self, ctx: ExtractionContext) -> bool:
        """Quick check if this extractor is relevant."""
        pass

    @abstractmethod
    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """Extract env vars and yield nodes/edges."""
        pass
