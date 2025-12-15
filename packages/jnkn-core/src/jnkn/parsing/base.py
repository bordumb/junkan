"""
Base Parser Infrastructure.

This module defines the foundational abstractions for the parsing subsystem.
It establishes the `LanguageParser` base class, the `ParseResult` container,
the unified `Extractor` protocol, and the `NodeFactory` helper for consistent
node creation.

Architecture Goals:
    - Every Node MUST have a `path` set to enable "Open in Editor" functionality
    - Extractors use `NodeFactory` to create nodes with guaranteed field population
    - `ExtractionContext` carries file information that extractors inherit
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Protocol, Set, Union

from ..core.interfaces import IParser
from ..core.types import Edge, Node, NodeType, RelationshipType

logger = logging.getLogger(__name__)


# =============================================================================
# Parser Context
# =============================================================================


class ParserContext:
    """
    Configuration context passed to parsers.

    Holds global settings that affect how files are parsed, such as the
    root directory (for computing relative paths) and default encoding.

    Attributes:
        root_dir: The root directory of the scan (used for relativizing paths).
        encoding: Default file encoding to use when decoding bytes.
    """

    def __init__(self, root_dir: Path | None = None):
        """
        Initialize parser context.

        Args:
            root_dir: The root directory for the scan. Defaults to cwd.
        """
        self.root_dir = root_dir or Path.cwd()
        self.encoding = "utf-8"


# =============================================================================
# Parse Result & Errors
# =============================================================================


@dataclass
class ParseError:
    """
    Represents a non-fatal error encountered during parsing.

    These errors are collected but do not halt the parsing process,
    allowing partial results to be captured.

    Attributes:
        file_path: The file where the error occurred.
        message: Description of the error.
        error_type: Category of error (e.g., 'syntax', 'encoding').
        recoverable: Whether parsing continued despite the error.
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

    Attributes:
        file_path: Path to the parsed file.
        file_hash: Content hash for incremental scanning.
        nodes: List of extracted Node objects.
        edges: List of extracted Edge objects.
        errors: List of error messages (strings).
        parse_errors: List of structured ParseError objects.
        metadata: Additional parser-specific metadata.
        success: Whether parsing completed without fatal errors.
        capabilities_used: Which parser capabilities were exercised.
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
    """
    Enumeration of capabilities a parser can provide.

    Used for documentation and capability-based filtering.
    """

    DEPENDENCIES = "dependencies"
    ENV_VARS = "env_vars"
    DATA_LINEAGE = "data_lineage"
    IMPORTS = "imports"
    DEFINITIONS = "definitions"
    CONFIGS = "configs"
    SECRETS = "secrets"
    OUTPUTS = "outputs"


# =============================================================================
# Extraction Context with NodeFactory
# =============================================================================


@dataclass
class ExtractionContext:
    """
    Context object passed to Extractors during processing.

    Provides access to the file content, path, and shared state needed
    by individual extractor implementations. Also serves as a factory
    for creating nodes with consistent field population.

    The key architectural improvement is that ALL nodes created via
    this context will have `path` automatically set, ensuring the
    "Open in Editor" feature works correctly in the visualization.

    Attributes:
        file_path: Absolute or relative path to the source file.
        file_id: The node ID for the file (e.g., "file://path/to/file.py").
        text: The decoded text content of the file.
        tree: Optional Tree-sitter AST object for advanced parsing.
        seen_ids: Set of IDs already emitted (for deduplication).
    """

    file_path: Path
    file_id: str
    text: str
    tree: Any | None = None
    seen_ids: Set[str] = field(default_factory=set)

    # -------------------------------------------------------------------------
    # Node Factory Methods
    # -------------------------------------------------------------------------

    def create_node(
        self,
        *,
        id: str,
        name: str,
        type: NodeType,
        line: int | None = None,
        tokens: List[str] | None = None,
        metadata: Dict[str, Any] | None = None,
        language: str | None = None,
    ) -> Node:
        """
        Create a Node with `path` automatically set from context.

        This is the core factory method that ensures every node has
        a valid `path` field, enabling the "Open in Editor" feature.

        Args:
            id: Unique identifier for the node.
            name: Human-readable name.
            type: The NodeType enum value.
            line: Optional line number in the source file.
            tokens: Optional list of tokens for fuzzy matching.
            metadata: Optional additional metadata dict.
            language: Optional language identifier.

        Returns:
            Node: A fully populated Node object with path set.
        """
        meta = metadata.copy() if metadata else {}
        if line is not None:
            meta["line"] = line

        # Ensure tokens is never None to satisfy Pydantic validation
        # Node model expects List[str], defaulting to empty list if None
        safe_tokens = tokens if tokens is not None else []

        return Node(
            id=id,
            name=name,
            type=type,
            path=str(self.file_path),
            language=language,
            tokens=safe_tokens,
            metadata=meta,
        )

    def create_env_var_node(
        self,
        *,
        name: str,
        line: int,
        source: str,
        default_value: str | None = None,
        extra_metadata: Dict[str, Any] | None = None,
    ) -> Node:
        """
        Create an environment variable node with standardized fields.

        Args:
            name: The environment variable name (e.g., "DATABASE_URL").
            line: Line number where the env var is referenced.
            source: The pattern/method that detected it (e.g., "os.getenv").
            default_value: Optional default value if specified in code.
            extra_metadata: Additional metadata to merge.

        Returns:
            Node: An ENV_VAR node with path and line set.
        """
        env_id = f"env:{name}"
        tokens = self._tokenize(name)

        meta = {
            "source": source,
            "line": line,
        }
        if default_value is not None:
            meta["default_value"] = default_value
        if extra_metadata:
            meta.update(extra_metadata)

        return Node(
            id=env_id,
            name=name,
            type=NodeType.ENV_VAR,
            path=str(self.file_path),
            tokens=tokens,
            metadata=meta,
        )

    def create_config_node(
        self,
        *,
        id: str,
        name: str,
        line: int | None = None,
        config_type: str = "config",
        extra_metadata: Dict[str, Any] | None = None,
    ) -> Node:
        """
        Create a configuration key node.

        Args:
            id: Unique identifier (e.g., "config:spark:spark.executor.memory").
            name: The config key name.
            line: Optional line number.
            config_type: Type of config (e.g., "terraform", "spark").
            extra_metadata: Additional metadata.

        Returns:
            Node: A CONFIG_KEY node.
        """
        tokens = self._tokenize(name)

        meta = {"config_type": config_type}
        if line is not None:
            meta["line"] = line
        if extra_metadata:
            meta.update(extra_metadata)

        return Node(
            id=id,
            name=name,
            type=NodeType.CONFIG_KEY,
            path=str(self.file_path),
            tokens=tokens,
            metadata=meta,
        )

    def create_data_asset_node(
        self,
        *,
        id: str,
        name: str,
        line: int | None = None,
        asset_type: str = "table",
        extra_metadata: Dict[str, Any] | None = None,
    ) -> Node:
        """
        Create a data asset node (table, file, topic, etc.).

        Args:
            id: Unique identifier (e.g., "data:schema.table_name").
            name: The asset name.
            line: Optional line number.
            asset_type: Type of asset (e.g., "table", "parquet", "topic").
            extra_metadata: Additional metadata.

        Returns:
            Node: A DATA_ASSET node.
        """
        tokens = self._tokenize(name)

        meta = {"asset_type": asset_type}
        if line is not None:
            meta["line"] = line
        if extra_metadata:
            meta.update(extra_metadata)

        return Node(
            id=id,
            name=name,
            type=NodeType.DATA_ASSET,
            path=str(self.file_path),
            tokens=tokens,
            metadata=meta,
        )

    def create_infra_node(
        self,
        *,
        id: str,
        name: str,
        line: int | None = None,
        infra_type: str = "resource",
        extra_metadata: Dict[str, Any] | None = None,
    ) -> Node:
        """
        Create an infrastructure resource node.

        Args:
            id: Unique identifier (e.g., "infra:aws_s3_bucket.my_bucket").
            name: The resource name.
            line: Optional line number.
            infra_type: Type of resource (e.g., "aws_s3_bucket").
            extra_metadata: Additional metadata.

        Returns:
            Node: An INFRA_RESOURCE node.
        """
        tokens = self._tokenize(name)

        meta = {"infra_type": infra_type}
        if line is not None:
            meta["line"] = line
        if extra_metadata:
            meta.update(extra_metadata)

        return Node(
            id=id,
            name=name,
            type=NodeType.INFRA_RESOURCE,
            path=str(self.file_path),
            tokens=tokens,
            metadata=meta,
        )

    def create_code_entity_node(
        self,
        *,
        name: str,
        line: int,
        entity_type: str = "function",
        language: str | None = None,
        extra_metadata: Dict[str, Any] | None = None,
    ) -> Node:
        """
        Create a code entity node (function, class, etc.).

        Args:
            name: The entity name.
            line: Line number of the definition.
            entity_type: Type of entity (e.g., "function", "class", "method").
            language: Programming language.
            extra_metadata: Additional metadata.

        Returns:
            Node: A CODE_ENTITY node.
        """
        entity_id = f"entity:{self.file_path}:{name}"

        meta = {
            "entity_type": entity_type,
            "line": line,
        }
        if extra_metadata:
            meta.update(extra_metadata)

        return Node(
            id=entity_id,
            name=name,
            type=NodeType.CODE_ENTITY,
            path=str(self.file_path),
            language=language,
            metadata=meta,
        )

    # -------------------------------------------------------------------------
    # Edge Factory Methods
    # -------------------------------------------------------------------------

    def create_reads_edge(
        self,
        *,
        target_id: str,
        line: int | None = None,
        pattern: str | None = None,
    ) -> Edge:
        """
        Create a READS edge from the current file to a target.

        Args:
            target_id: The ID of the node being read.
            line: Optional line number.
            pattern: Optional pattern that detected the read.

        Returns:
            Edge: A READS relationship edge.
        """
        meta = {}
        if line is not None:
            meta["line"] = line
        if pattern is not None:
            meta["pattern"] = pattern

        return Edge(
            source_id=self.file_id,
            target_id=target_id,
            type=RelationshipType.READS,
            metadata=meta if meta else None,
        )

    def create_contains_edge(self, *, target_id: str) -> Edge:
        """
        Create a CONTAINS edge from the current file to a target.

        Args:
            target_id: The ID of the contained node.

        Returns:
            Edge: A CONTAINS relationship edge.
        """
        return Edge(
            source_id=self.file_id,
            target_id=target_id,
            type=RelationshipType.CONTAINS,
        )

    # -------------------------------------------------------------------------
    # Utility Methods
    # -------------------------------------------------------------------------

    def get_line_number(self, position: int) -> int:
        """
        Calculate line number from character position.

        Args:
            position: Character offset in the text.

        Returns:
            int: 1-indexed line number.
        """
        return self.text[:position].count("\n") + 1

    def mark_seen(self, identifier: str) -> bool:
        """
        Check if an identifier has been seen and mark it if not.

        This is useful for deduplication across extractors.

        Args:
            identifier: The identifier to check/mark.

        Returns:
            bool: True if this is the first time seeing this ID, False otherwise.
        """
        if identifier in self.seen_ids:
            return False
        self.seen_ids.add(identifier)
        return True

    def _tokenize(self, name: str) -> List[str]:
        """
        Tokenize a name for fuzzy matching.

        Splits on underscores, hyphens, dots, and camelCase boundaries.

        Args:
            name: The name to tokenize.

        Returns:
            List[str]: List of lowercase tokens (min length 2).
        """
        # Split on separators
        parts = re.split(r"[_\-./]", name)

        # Also split camelCase
        tokens = []
        for part in parts:
            # Insert splits before uppercase letters (camelCase)
            camel_parts = re.sub(r"([a-z])([A-Z])", r"\1_\2", part).split("_")
            tokens.extend(camel_parts)

        # Filter and lowercase
        return [t.lower() for t in tokens if len(t) >= 2]


# =============================================================================
# Extractor Protocol & Base Class
# =============================================================================


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
    Subclasses should use the factory methods on ExtractionContext to create
    nodes, ensuring consistent field population.
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


# =============================================================================
# Extractor Registry
# =============================================================================


class ExtractorRegistry:
    """
    Registry for managing and executing a collection of Extractors.

    Extractors are sorted by priority (highest first) and executed
    sequentially. Failures in individual extractors are logged but
    do not halt the extraction process.
    """

    def __init__(self):
        """Initialize an empty registry."""
        self._extractors: List[Extractor] = []

    def register(self, extractor: Extractor) -> None:
        """
        Register an extractor and maintain priority sort order.

        Args:
            extractor: The extractor to register.
        """
        self._extractors.append(extractor)
        self._extractors.sort(key=lambda e: -e.priority)

    def extract_all(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """
        Execute all registered extractors against the provided context.

        Failures in individual extractors are logged but do not halt the process.

        Args:
            ctx: The extraction context.

        Yields:
            Node and Edge objects from all applicable extractors.
        """
        for extractor in self._extractors:
            if extractor.can_extract(ctx):
                try:
                    yield from extractor.extract(ctx)
                except Exception as e:
                    logger.debug(f"Extractor {extractor.name} failed on {ctx.file_path}: {e}")


# =============================================================================
# Language Parser Base Class
# =============================================================================


class LanguageParser(IParser, ABC):
    """
    Abstract Base Class for language-specific parsers.

    Implementations must define supported extensions and the parsing logic.
    The parser is responsible for creating the file node and delegating
    to extractors for content-specific extraction.

    Attributes:
        context: The parser context with global settings.
    """

    def __init__(self, context: ParserContext | None = None):
        """
        Initialize the parser.

        Args:
            context: Optional parser context. Defaults to a new context.
        """
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

        Returns:
            bool: True if this parser can handle the file.
        """
        pass

    @abstractmethod
    def parse(self, file_path: Path, content: bytes) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse the file and yield Nodes and Edges.

        Args:
            file_path: Path to the file.
            content: Raw bytes of the file.

        Yields:
            Node and Edge objects extracted from the file.
        """
        pass

    def parse_full(self, file_path: Path, content: bytes | None = None) -> ParseResult:
        """
        Parse a file and wrap the output in a standardized ParseResult.

        Handles exceptions and file reading if content is not provided.

        Args:
            file_path: Path to the file.
            content: Optional file content. Read from disk if not provided.

        Returns:
            ParseResult: A result object containing nodes, edges, and errors.
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
        """
        Return the path relative to the scan root, or absolute if not possible.

        Args:
            path: The path to relativize.

        Returns:
            str: The relativized path string.
        """
        try:
            return str(path.relative_to(self.context.root_dir))
        except ValueError:
            return str(path)


# =============================================================================
# Composite Parser
# =============================================================================


class CompositeParser(LanguageParser):
    """
    A parser that delegates to multiple sub-parsers.

    Useful for handling directories or mixed-content scenarios where
    multiple parsers might apply to the same file type.
    """

    def __init__(self, context: ParserContext, parsers: List[LanguageParser]):
        """
        Initialize the composite parser.

        Args:
            context: The parser context.
            parsers: List of sub-parsers to delegate to.
        """
        super().__init__(context)
        self.parsers = parsers

    @property
    def name(self) -> str:
        """Return 'composite' as the parser name."""
        return "composite"

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        """
        Check if any sub-parser can handle the file.

        Args:
            file_path: Path to the file.
            content: Optional file content.

        Returns:
            bool: True if any sub-parser can parse.
        """
        return any(p.can_parse(file_path, content) for p in self.parsers)

    def parse(self, file_path: Path, content: bytes) -> Generator[Union[Node, Edge], None, None]:
        """
        Delegate parsing to all applicable sub-parsers.

        Args:
            file_path: Path to the file.
            content: Raw bytes of the file.

        Yields:
            Node and Edge objects from all applicable parsers.
        """
        for parser in self.parsers:
            if parser.can_parse(file_path, content):
                yield from parser.parse(file_path, content)
