"""
Base Parser Infrastructure.

Defines the core classes and types for the parsing system:
- LanguageParser: Abstract base for all parsers
- ParseResult: Standardized output container
- ParseError: Error tracking
- ParserCapability: Feature flags
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ..core.interfaces import IParser
from ..core.types import Edge, Node


class ParserContext:
    """Context passed to parsers (e.g., root directory)."""
    def __init__(self, root_dir: Optional[Path] = None):
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


class LanguageParser(IParser, ABC):
    """
    Abstract Base Class for all language parsers.
    
    Enforces strict typing of return values and provides common utilities.
    """

    def __init__(self, context: Optional[ParserContext] = None):
        self.context = context or ParserContext()
        # Initialize logger for all subclasses
        import logging
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique name of this parser (e.g., 'python', 'terraform')."""
        pass

    @property
    def extensions(self) -> List[str]:
        """List of file extensions this parser supports."""
        return []

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
    
    def parse_full(self, file_path: Path, content: Optional[bytes] = None) -> ParseResult:
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
            errors=errors
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

    def can_parse(self, file_path: Path) -> bool:
        return any(p.can_parse(file_path) for p in self.parsers)

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results = []
        for parser in self.parsers:
            if parser.can_parse(file_path):
                results.extend(parser.parse(file_path, content))
        return results