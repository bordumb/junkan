"""
Base classes for the Jnkn parsing framework.

This module defines the fundamental abstractions used to ingest source code
and convert it into a dependency graph. It provides the interface that all
language-specific parsers must implement.

Key Components:
    LanguageParser: Abstract base class for all parsers.
    ParserContext: Runtime configuration and state shared across parsers.
    ParseResult: Container for nodes, edges, and errors from a single file.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Union

from ..core.types import Edge, Node


class ParserCapability(Enum):
    """
    Enumeration of capabilities a parser can support.

    These flags allow the engine to intelligently route files or
    optimize scanning passes based on what information is needed.
    """
    IMPORTS = auto()        #: Can extract import statements
    DEFINITIONS = auto()    #: Can extract function/class definitions
    ENV_VARS = auto()       #: Can extract environment variable usage
    RESOURCES = auto()      #: Can extract infrastructure resources
    DEPENDENCIES = auto()   #: Can extract abstract dependency relationships
    DATA_LINEAGE = auto()   #: Can extract data lineage (e.g., dbt refs)
    CALLS = auto()          #: Can extract function calls
    TYPES = auto()          #: Can extract type annotations
    CONFIGS = auto()        #: Can extract configuration keys
    SECRETS = auto()        #: Can extract secret references


@dataclass
class ParserContext:
    """
    Context provided to parsers during execution.

    This object is passed down to every parser instance, allowing them to access
    global configuration, the project root, or shared state without coupling.

    Attributes:
        root_dir (Path): The root directory of the project being scanned.
            Defaults to current working directory.
        current_file (Optional[Path]): The specific file currently being processed.
        config (Dict[str, Any]): Global configuration dictionary (from config.yaml).
        seen_files (Set[Path]): Tracks files already processed to prevent cycles.
        encoding (str): Default file encoding to use when reading files.
    """
    root_dir: Path = field(default_factory=Path.cwd)
    current_file: Optional[Path] = None
    config: Dict[str, Any] = field(default_factory=dict)
    seen_files: Set[Path] = field(default_factory=set)
    encoding: str = "utf-8"

    def relative_path(self, path: Path) -> Path:
        """
        Convert an absolute path to a path relative to the project root.

        Args:
            path (Path): The absolute path to convert.

        Returns:
            Path: The relative path if within root_dir, else the original path.
        """
        try:
            return path.relative_to(self.root_dir)
        except ValueError:
            return path


@dataclass
class ParseResult:
    """
    The result of parsing a single source file.

    Aggregates all discovered nodes, edges, and any errors encountered
    during the parsing process.

    Attributes:
        file_path (Path): Path to the source file that was parsed.
        nodes (List[Node]): All graph nodes extracted from the file.
        edges (List[Edge]): All relationships discovered in the file.
        errors (List[str]): Any non-fatal error messages generated.
        metadata (Dict[str, Any]): Additional metadata (e.g., parser version, skip reason).
    """
    file_path: Path
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """
        Check if parsing completed without errors.

        Returns:
            bool: True if there are no errors, False otherwise.
        """
        return len(self.errors) == 0

    def add_node(self, node: Node) -> None:
        """
        Register a new node in the result.

        Args:
            node (Node): The node entity to add.
        """
        self.nodes.append(node)

    def add_edge(self, edge: Edge) -> None:
        """
        Register a new edge in the result.

        Args:
            edge (Edge): The relationship edge to add.
        """
        self.edges.append(edge)

    def add_error(self, error: str) -> None:
        """
        Log a non-fatal parsing error.

        Args:
            error (str): Descriptive error message.
        """
        self.errors.append(error)


class ParseError(Exception):
    """
    Exception raised when a parser encounters a fatal error.

    Attributes:
        message (str): The error description.
        file_path (Optional[Path]): The file being processed when error occurred.
        line (Optional[int]): Line number of the error.
        column (Optional[int]): Column number of the error.
    """
    def __init__(
        self,
        message: str,
        file_path: Optional[Path] = None,
        line: Optional[int] = None,
        column: Optional[int] = None,
    ):
        self.message = message
        self.file_path = file_path
        self.line = line
        self.column = column

        location = ""
        if file_path:
            location = f" in {file_path}"
            if line is not None:
                location += f":{line}"
                if column is not None:
                    location += f":{column}"

        super().__init__(f"{message}{location}")


class LanguageParser(ABC):
    """
    Abstract base class for all language parsers.

    To support a new language, subclass this and implement the `parse` method.
    The `can_parse` method serves as a filter to determine if this parser
    should handle a given file.

    Args:
        context (Optional[ParserContext]): The execution context.
    """

    def __init__(self, context: Optional[ParserContext] = None):
        self._context = context or ParserContext()

    @property
    def context(self) -> ParserContext:
        """Get the current parser context."""
        return self._context

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the unique identifier for this parser.

        Returns:
            str: A unique slug (e.g., 'python', 'terraform').
        """
        pass

    @property
    @abstractmethod
    def extensions(self) -> Set[str]:
        """
        Get the file extensions supported by this parser.

        Returns:
            Set[str]: A set of extensions including the dot (e.g., {'.py', '.pyi'}).
        """
        pass

    def can_parse(self, file_path: Path, content: Optional[bytes] = None) -> bool:
        """
        Determine if this parser can handle the given file.

        The default implementation checks the file extension against `self.extensions`.
        Subclasses may override this to implement heuristic detection (e.g., checking
        file contents for shebangs or specific keywords).

        Args:
            file_path (Path): The path to the file.
            content (Optional[bytes]): The raw file content (if already read).

        Returns:
            bool: True if the parser can process this file.
        """
        return file_path.suffix.lower() in self.extensions

    @abstractmethod
    def parse(
        self,
        file_path: Path,
        content: bytes,
        context: Optional[ParserContext] = None,
    ) -> Iterator[Union[Node, Edge]]:
        """
        Parse a file and generate graph elements.

        This is the core logic method that must be implemented by subclasses.

        Args:
            file_path (Path): The path to the source file.
            content (bytes): The raw file content.
            context (Optional[ParserContext]): Context override for this specific operation.

        Yields:
            Union[Node, Edge]: Extracted nodes and edges.
        """
        pass

    def get_capabilities(self) -> Set[ParserCapability]:
        """
        Get the set of capabilities supported by this parser.

        Returns:
            Set[ParserCapability]: A set of capability flags.
        """
        return set()

    def supports_capability(self, capability: ParserCapability) -> bool:
        """
        Check if the parser supports a specific capability.

        Args:
            capability (ParserCapability): The capability to check.

        Returns:
            bool: True if supported.
        """
        return capability in self.get_capabilities()

    def parse_file(
        self,
        file_path: Path,
        context: Optional[ParserContext] = None,
    ) -> ParseResult:
        """
        Utility method to read and parse a file from disk.

        This wraps the `parse` generator, handles file I/O, and catches exceptions
        to return a structured `ParseResult` object.

        Args:
            file_path (Path): Path to the file.
            context (Optional[ParserContext]): Context override.

        Returns:
            ParseResult: The result object containing nodes, edges, and errors.
        """
        result = ParseResult(file_path=file_path)

        try:
            content = file_path.read_bytes()

            for item in self.parse(file_path, content, context):
                if isinstance(item, Node):
                    result.add_node(item)
                elif isinstance(item, Edge):
                    result.add_edge(item)

        except ParseError as e:
            result.add_error(str(e))
        except Exception as e:
            result.add_error(f"Unexpected error: {e}")

        return result


class CompositeParser(LanguageParser):
    """
    A meta-parser that delegates to a list of sub-parsers.

    Useful when a language requires multiple parsing strategies (e.g., trying
    Tree-sitter first, then falling back to Regex).
    """

    def __init__(
        self,
        name: str,
        extensions: Set[str],
        parsers: List[LanguageParser],
        context: Optional[ParserContext] = None,
    ):
        """
        Initialize the composite parser.

        Args:
            name (str): Unique name for this composite.
            extensions (Set[str]): Supported extensions.
            parsers (List[LanguageParser]): List of sub-parsers to try in order.
            context (Optional[ParserContext]): Execution context.
        """
        super().__init__(context)
        self._name = name
        self._extensions = extensions
        self._parsers = parsers

    @property
    def name(self) -> str:
        return self._name

    @property
    def extensions(self) -> Set[str]:
        return self._extensions

    def parse(
        self,
        file_path: Path,
        content: bytes,
        context: Optional[ParserContext] = None,
    ) -> Iterator[Union[Node, Edge]]:
        """
        Execute parsing by delegating to sub-parsers.

        Sub-parsers are tried in the order provided. All successful results are yielded.
        Nodes are deduplicated by ID to prevent redundancy.
        """
        seen_ids: Set[str] = set()

        for parser in self._parsers:
            try:
                if parser.can_parse(file_path, content):
                    for item in parser.parse(file_path, content, context):
                        item_id = getattr(item, 'id', None) or id(item)
                        if item_id not in seen_ids:
                            seen_ids.add(item_id)
                            yield item
            except ParseError:
                continue
            except Exception:
                continue

    def get_capabilities(self) -> Set[ParserCapability]:
        """Return the union of all sub-parser capabilities."""
        capabilities: Set[ParserCapability] = set()
        for parser in self._parsers:
            capabilities.update(parser.get_capabilities())
        return capabilities
