"""
Base Parser Infrastructure.

This module defines the foundational abstractions for the parsing subsystem.
It establishes the `LanguageParser` base class, the `ParseResult` container,
and the unified `Extractor` protocol used to implement language-specific logic.
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
    """
    Configuration context passed to parsers.

    Attributes:
        root_dir (Path): The root directory of the scan.
        encoding (str): Default file encoding to use.
    """

    def __init__(self, root_dir: Path | None = None):
        self.root_dir = root_dir or Path.cwd()
        self.encoding = "utf-8"


@dataclass
class ParseError:
    """
    Represents a non-fatal error encountered during parsing.

    Attributes:
        file_path (str): The file where the error occurred.
        message (str): Description of the error.
        error_type (str): Category of error (e.g., 'syntax', 'encoding').
        recoverable (bool): Whether parsing continued despite the error.
    """

    file_path: str
    message: str
    error_type: str = "general"
    recoverable: bool = True


@dataclass
class ParseResult:
    """
    The standardized result object returned by all parsers.

    Encapsulates the nodes and edges extracted from a file, along with
    metadata and any errors encountered during the process.
    """

    file_path: Path
    file_hash: str
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    parse_errors: List[ParseError] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    capabilities_used: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Automatically set success=False if errors are present."""
        if self.errors or self.parse_errors:
            self.success = False


class ParserCapability:
    """Enumeration of capabilities a parser can provide."""

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
    Context object passed to Extractors during processing.

    Provides access to the file content, path, and shared state (like deduplication sets)
    needed by individual extractor implementations.
    """

    file_path: Path
    file_id: str
    text: str
    tree: Any | None = None  # Tree-sitter AST object
    seen_ids: Set[str] = field(default_factory=set)


class Extractor(Protocol):
    """
    Protocol for implementing modular extraction logic.

    Extractors are specialized components (e.g., 'EnvVarExtractor', 'ImportExtractor')
    that focus on finding specific patterns within a source file.
    """

    @property
    def name(self) -> str:
        """Unique identifier for the extractor (for debugging)."""
        ...

    @property
    def priority(self) -> int:
        """Execution priority (0-100). Higher runs first."""
        ...

    def can_extract(self, ctx: ExtractionContext) -> bool:
        """Determine if this extractor applies to the current context."""
        ...

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """Yield Nodes and Edges found in the source text."""
        ...


class BaseExtractor(ABC):
    """
    Abstract base class for extractors.

    Provides a standard inheritance base for implementing the Extractor protocol.
    """

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
        """Extract artifacts and yield nodes/edges."""
        pass


class ExtractorRegistry:
    """
    Registry for managing and executing a collection of Extractors.
    """

    def __init__(self):
        self._extractors: List[Extractor] = []

    def register(self, extractor: Extractor) -> None:
        """Register an extractor and maintain priority sort order."""
        self._extractors.append(extractor)
        self._extractors.sort(key=lambda e: -e.priority)

    def extract_all(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """
        Execute all registered extractors against the provided context.
        Failures in individual extractors are logged but do not halt the process.
        """
        for extractor in self._extractors:
            if extractor.can_extract(ctx):
                try:
                    yield from extractor.extract(ctx)
                except Exception as e:
                    logger.debug(f"Extractor {extractor.name} failed on {ctx.file_path}: {e}")


class LanguageParser(IParser, ABC):
    """
    Abstract Base Class for language-specific parsers.

    Implementations must define supported extensions and the parsing logic.
    """

    def __init__(self, context: ParserContext | None = None):
        self.context = context or ParserContext()
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    @abstractmethod
    def name(self) -> str:
        """The unique name of the language (e.g., 'python')."""
        pass

    @property
    def extensions(self) -> List[str]:
        """List of file extensions supported by this parser."""
        return []

    @abstractmethod
    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        """
        Determine if the file can be parsed.

        Args:
            file_path: The path to the file.
            content: Optional file content for heuristic detection.
        """
        pass

    @abstractmethod
    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        """Parse the file and return a list of Nodes and Edges."""
        pass

    def parse_full(self, file_path: Path, content: bytes | None = None) -> ParseResult:
        """
        Parse a file and wrap the output in a standardized ParseResult.

        Handles exceptions and file reading if content is not provided.
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
            file_hash="",  # Hash is usually computed by the engine
            nodes=nodes,
            edges=edges,
            errors=errors,
        )

    def _relativize(self, path: Path) -> str:
        """Return the path relative to the scan root, or absolute if not possible."""
        try:
            return str(path.relative_to(self.context.root_dir))
        except ValueError:
            return str(path)


class CompositeParser(LanguageParser):
    """
    A parser that delegates to multiple sub-parsers.
    Useful for handling directories or mixed-content scenarios.
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
