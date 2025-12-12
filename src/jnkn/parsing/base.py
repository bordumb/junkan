"""
Base Parser Infrastructure.

Defines the core classes and types for the parsing system, including the
unified Extractor pattern used to standardize parsing logic across languages.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Protocol, Set, Union

from ..core.interfaces import IParser
from ..core.types import Edge, Node

logger = logging.getLogger(__name__)


class ParserContext:
    """Context passed to parsers (e.g., root directory)."""

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or Path.cwd()
        self.encoding = "utf-8"


@dataclass
class ParseError:
    """Represents a non-fatal error during parsing."""

    file_path: str
    message: str
    error_type: str = "general"
    recoverable: bool = True


@dataclass
class ParseResult:
    """
    Standardized result object returned by all parsers.

    Contains the extracted nodes, edges, and any errors encountered.
    """

    file_path: Path
    file_hash: str
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)  # String messages
    parse_errors: List[ParseError] = field(default_factory=list)  # Structured errors
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    capabilities_used: List[str] = field(default_factory=list)

    def __post_init__(self):
        if self.errors or self.parse_errors:
            self.success = False


class ParserCapability:
    """Enum-like constants for parser capabilities."""

    DEPENDENCIES = "dependencies"
    ENV_VARS = "env_vars"
    DATA_LINEAGE = "data_lineage"
    IMPORTS = "imports"
    DEFINITIONS = "definitions"
    CONFIGS = "configs"
    SECRETS = "secrets"
    OUTPUTS = "outputs"


@dataclass
class ExtractionContext:
    """
    Shared context for all extractors processing a single file.

    This context is immutable during the extraction phase of a specific file
    and allows different extractors (Regex, Tree-sitter, etc.) to access
    the same underlying data.
    """

    file_path: Path
    file_id: str
    text: str
    tree: Any | None = None  # Tree-sitter AST object
    seen_ids: Set[str] = field(default_factory=set)  # Deduplication across extractors


class Extractor(Protocol):
    """
    Universal extractor interface.

    Any class implementing this protocol can be registered to a LanguageParser
    to extract nodes and edges from source files.
    """

    @property
    def name(self) -> str:
        """Unique name for debugging."""
        ...

    @property
    def priority(self) -> int:
        """Execution priority. Higher numbers run first."""
        ...

    def can_extract(self, ctx: ExtractionContext) -> bool:
        """Quick check to see if this extractor applies to the current file context."""
        ...

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """Generator yielding Nodes and Edges found in the context."""
        ...


class ExtractorRegistry:
    """
    Manages and orchestrates extractors for a specific language parser.
    """

    def __init__(self):
        self._extractors: List[Extractor] = []

    def register(self, extractor: Extractor) -> None:
        """Register a new extractor and sort by priority."""
        self._extractors.append(extractor)
        # Sort descending by priority (100 -> 0)
        self._extractors.sort(key=lambda e: -e.priority)

    def extract_all(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """Run all registered extractors against the context."""
        for extractor in self._extractors:
            if extractor.can_extract(ctx):
                try:
                    yield from extractor.extract(ctx)
                except Exception as e:
                    # Log but do not crash the entire parse operation
                    logger.debug(f"Extractor {extractor.name} failed on {ctx.file_path}: {e}")


class LanguageParser(IParser, ABC):
    """
    Abstract Base Class for all language parsers.
    """

    def __init__(self, context: ParserContext | None = None):
        self.context = context or ParserContext()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @property
    def extensions(self) -> List[str]:
        return []

    @abstractmethod
    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        pass

    @abstractmethod
    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        pass

    def parse_full(self, file_path: Path, content: bytes | None = None) -> ParseResult:
        """
        Convenience method to parse and return a full ParseResult object.
        Used by the engine to wrap results.
        """
        nodes = []
        edges = []
        errors = []

        try:
            if content is None:
                content = file_path.read_bytes()

            for item in self.parse(file_path, content):
                if isinstance(item, Node):
                    nodes.append(item)
                elif isinstance(item, Edge):
                    edges.append(item)

        except Exception as e:
            errors.append(str(e))

        return ParseResult(
            file_path=file_path,
            file_hash="",  # Hash calculation is delegated to engine or pre-calculated
            nodes=nodes,
            edges=edges,
            errors=errors,
        )

    def _relativize(self, path: Path) -> str:
        """Helper to get path relative to project root."""
        try:
            return str(path.relative_to(self.context.root_dir))
        except ValueError:
            return str(path)


class CompositeParser(LanguageParser):
    """
    Parser that delegates to multiple sub-parsers.
    Used to handle directories or multiple file types.
    """

    @property
    def name(self) -> str:
        return "composite"

    def __init__(self, context: ParserContext, parsers: List[LanguageParser]):
        super().__init__(context)
        self.parsers = parsers

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        return any(p.can_parse(file_path, content) for p in self.parsers)

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results = []
        for parser in self.parsers:
            if parser.can_parse(file_path, content):
                results.extend(parser.parse(file_path, content))
        return results
