"""
Base classes for Jnkn parsers.

This module defines the abstract base classes and common types used by
all language-specific parsers in the Jnkn framework.

Key Components:
- LanguageParser: Abstract base class for all parsers
- ParserCapability: Enum of parser capabilities
- ParserContext: Context passed during parsing
- ParseResult: Result of parsing a file
- ParseError: Exception for parsing errors
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import (
    Dict, Generator, List, Optional, Set, Tuple,
    Union, Any, Iterator, Callable
)

from ..core.types import Node, Edge, NodeType, RelationshipType


class ParserCapability(Enum):
    """
    Capabilities that a parser may support.
    
    These capabilities help the engine understand what artifacts
    a parser can extract from source files.
    """
    IMPORTS = auto()        # Can extract import statements
    DEFINITIONS = auto()    # Can extract function/class definitions
    ENV_VARS = auto()       # Can extract environment variable usage
    RESOURCES = auto()      # Can extract infrastructure resources
    DEPENDENCIES = auto()   # Can extract dependency relationships
    DATA_LINEAGE = auto()   # Can extract data lineage (dbt, etc.)
    CALLS = auto()          # Can extract function calls
    TYPES = auto()          # Can extract type annotations


@dataclass
class ParserContext:
    """
    Context provided to parsers during parsing operations.
    
    Attributes:
        root_dir: The root directory of the project being scanned
        current_file: The file currently being parsed
        config: Optional configuration dictionary
        seen_files: Set of files already processed (for cycle detection)
        encoding: File encoding to use (default: utf-8)
    """
    root_dir: Path = field(default_factory=Path.cwd)
    current_file: Optional[Path] = None
    config: Dict[str, Any] = field(default_factory=dict)
    seen_files: Set[Path] = field(default_factory=set)
    encoding: str = "utf-8"
    
    def relative_path(self, path: Path) -> Path:
        """Get path relative to root_dir."""
        try:
            return path.relative_to(self.root_dir)
        except ValueError:
            return path


@dataclass
class ParseResult:
    """
    Result of parsing a single file.
    
    Attributes:
        file_path: Path to the parsed file
        nodes: List of nodes extracted from the file
        edges: List of edges extracted from the file
        errors: List of any errors encountered during parsing
        metadata: Additional metadata about the parse operation
    """
    file_path: Path
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def success(self) -> bool:
        """Return True if parsing succeeded without errors."""
        return len(self.errors) == 0
    
    def add_node(self, node: Node) -> None:
        """Add a node to the result."""
        self.nodes.append(node)
    
    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the result."""
        self.edges.append(edge)
    
    def add_error(self, error: str) -> None:
        """Add an error message."""
        self.errors.append(error)


class ParseError(Exception):
    """
    Exception raised when parsing fails.
    
    Attributes:
        message: Error message
        file_path: Path to the file that failed to parse
        line: Optional line number where the error occurred
        column: Optional column number where the error occurred
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
    Abstract base class for language-specific parsers.
    
    All parsers must implement this interface to be used with the
    ParserEngine.
    
    Example:
        class PythonParser(LanguageParser):
            def __init__(self, context: Optional[ParserContext] = None):
                super().__init__(context)
            
            @property
            def name(self) -> str:
                return "python"
            
            @property
            def extensions(self) -> Set[str]:
                return {".py", ".pyi"}
            
            def parse(self, file_path: Path, content: bytes) -> Iterator[Union[Node, Edge]]:
                # Parse implementation
                yield Node(...)
    """
    
    def __init__(self, context: Optional[ParserContext] = None):
        """
        Initialize the parser with optional context.
        
        Args:
            context: Optional parsing context with root directory and config
        """
        self._context = context or ParserContext()
    
    @property
    def context(self) -> ParserContext:
        """Get the parser's context."""
        return self._context
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Return the unique name of this parser.
        
        This name is used for registration and logging.
        """
        pass
    
    @property
    @abstractmethod
    def extensions(self) -> Set[str]:
        """
        Return the file extensions this parser handles.
        
        Extensions should include the leading dot (e.g., ".py").
        """
        pass
    
    @abstractmethod
    def parse(
        self,
        file_path: Path,
        content: bytes,
        context: Optional[ParserContext] = None,
    ) -> Iterator[Union[Node, Edge]]:
        """
        Parse a file and yield nodes and edges.
        
        Args:
            file_path: Path to the file being parsed
            content: Raw bytes content of the file
            context: Optional parsing context (overrides instance context)
        
        Yields:
            Node or Edge objects extracted from the file
        
        Raises:
            ParseError: If parsing fails
        """
        pass
    
    def get_capabilities(self) -> Set[ParserCapability]:
        """
        Return the capabilities this parser supports.
        
        Default implementation returns an empty set.
        Subclasses should override to declare capabilities.
        """
        return set()
    
    def supports_capability(self, capability: ParserCapability) -> bool:
        """Check if this parser supports a specific capability."""
        return capability in self.get_capabilities()
    
    def parse_file(
        self,
        file_path: Path,
        context: Optional[ParserContext] = None,
    ) -> ParseResult:
        """
        Parse a file from disk.
        
        Convenience method that reads the file and calls parse().
        
        Args:
            file_path: Path to the file to parse
            context: Optional parsing context
        
        Returns:
            ParseResult with nodes, edges, and any errors
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
    A parser that combines multiple sub-parsers.
    
    This is useful for languages that have multiple parsing strategies
    (e.g., tree-sitter + regex fallback).
    
    Example:
        parser = CompositeParser(
            name="python",
            extensions={".py"},
            parsers=[TreeSitterPythonParser(), RegexPythonParser()],
        )
    """
    
    def __init__(
        self,
        name: str,
        extensions: Set[str],
        parsers: List[LanguageParser],
        context: Optional[ParserContext] = None,
    ):
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
        Parse using sub-parsers in order.
        
        Each parser is tried in order. Results from all parsers are combined.
        """
        seen_ids: Set[str] = set()
        
        for parser in self._parsers:
            try:
                for item in parser.parse(file_path, content, context):
                    # Deduplicate by ID
                    item_id = getattr(item, 'id', None) or id(item)
                    if item_id not in seen_ids:
                        seen_ids.add(item_id)
                        yield item
            except ParseError:
                # Try next parser
                continue
            except Exception:
                # Try next parser on unexpected errors
                continue
    
    def get_capabilities(self) -> Set[ParserCapability]:
        """Return union of all sub-parser capabilities."""
        capabilities: Set[ParserCapability] = set()
        for parser in self._parsers:
            capabilities.update(parser.get_capabilities())
        return capabilities


# Type alias for parser factories
ParserFactory = Callable[[], LanguageParser]


def create_file_node(
    file_path: Path,
    root_dir: Optional[Path] = None,
    language: Optional[str] = None,
    file_hash: Optional[str] = None,
) -> Node:
    """
    Create a Node representing a source file.
    
    Args:
        file_path: Path to the file
        root_dir: Optional root directory for relative path
        language: Optional language identifier
        file_hash: Optional content hash
    
    Returns:
        Node with type CODE_FILE
    """
    if root_dir:
        try:
            rel_path = file_path.relative_to(root_dir)
        except ValueError:
            rel_path = file_path
    else:
        rel_path = file_path
    
    return Node(
        id=f"file://{rel_path}",
        name=file_path.name,
        type=NodeType.CODE_FILE,
        path=str(rel_path),
        language=language,
        file_hash=file_hash,
    )


def create_env_var_node(
    name: str,
    source_file: Optional[Path] = None,
    line: Optional[int] = None,
    pattern: Optional[str] = None,
) -> Node:
    """
    Create a Node representing an environment variable.
    
    Args:
        name: Name of the environment variable
        source_file: Optional file where it was found
        line: Optional line number
        pattern: Optional pattern used to detect it
    
    Returns:
        Node with type ENV_VAR
    """
    # Tokenize the env var name for stitching
    tokens = tuple(
        t.lower()
        for t in name.replace("_", " ").replace("-", " ").split()
        if len(t) >= 2
    )
    
    metadata: Dict[str, Any] = {}
    if source_file:
        metadata["source_file"] = str(source_file)
    if line:
        metadata["line"] = line
    if pattern:
        metadata["pattern"] = pattern
    
    return Node(
        id=f"env:{name}",
        name=name,
        type=NodeType.ENV_VAR,
        tokens=tokens,
        metadata=metadata,
    )


def create_import_edge(
    source_file_id: str,
    target_module: str,
    import_type: str = "import",
) -> Edge:
    """
    Create an Edge representing an import relationship.
    
    Args:
        source_file_id: ID of the file doing the import
        target_module: Module being imported
        import_type: Type of import (import, from_import, etc.)
    
    Returns:
        Edge with type IMPORTS
    """
    return Edge(
        source_id=source_file_id,
        target_id=f"module:{target_module}",
        type=RelationshipType.IMPORTS,
        metadata={"import_type": import_type},
    )