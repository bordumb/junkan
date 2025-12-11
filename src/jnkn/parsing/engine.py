"""
Parser Engine for jnkn.

This module provides the central orchestration for all parsing activities.
It manages parser registration, file routing, and result aggregation.

Key Components:
- ParserEngine: Main orchestrator for parsing operations
- ParserRegistry: Plugin-style parser registration

Design Principles:
1. Plugin architecture via entry points
2. Extension-based routing to appropriate parsers
3. Lazy initialization of parsers
4. Batch processing support for performance
"""

import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Set, Type, Union

from ..core.types import Edge, Node, ScanMetadata
from .base import (
    LanguageParser,
    ParseError,
    ParserContext,
    ParseResult,
)

logger = logging.getLogger(__name__)


# Default directories to skip during scanning
DEFAULT_SKIP_DIRS: Set[str] = {
    ".git", ".jnkn", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".env", "dist", "build",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    ".tox", ".nox", ".coverage", "htmlcov",
    "target", "out", "bin", ".idea", ".vscode",
}


# Default file patterns to skip
DEFAULT_SKIP_PATTERNS: Set[str] = {
    "*.pyc", "*.pyo", "*.so", "*.dll",
    "*.min.js", "*.bundle.js", "*.map",
    "*.lock", "*.log",
}


@dataclass
class ScanConfig:
    """
    Configuration for scanning operations.
    
    Attributes:
        root_dir: Root directory to scan
        skip_dirs: Directories to skip
        skip_patterns: File patterns to skip
        file_extensions: Only scan files with these extensions (empty = all)
        max_files: Maximum number of files to scan (0 = unlimited)
        follow_symlinks: Whether to follow symbolic links
        incremental: Use incremental scanning based on file hashes
    """
    root_dir: Path = field(default_factory=lambda: Path.cwd())
    skip_dirs: Set[str] = field(default_factory=lambda: DEFAULT_SKIP_DIRS.copy())
    skip_patterns: Set[str] = field(default_factory=lambda: DEFAULT_SKIP_PATTERNS.copy())
    file_extensions: Set[str] = field(default_factory=set)
    max_files: int = 0
    follow_symlinks: bool = False
    incremental: bool = True

    def should_skip_dir(self, dir_name: str) -> bool:
        """Check if a directory should be skipped."""
        return dir_name in self.skip_dirs

    def should_skip_file(self, file_path: Path) -> bool:
        """Check if a file should be skipped."""
        from fnmatch import fnmatch
        name = file_path.name
        return any(fnmatch(name, pattern) for pattern in self.skip_patterns)


@dataclass
class ScanStats:
    """
    Statistics from a scan operation.
    """
    files_scanned: int = 0
    files_skipped: int = 0
    files_unchanged: int = 0
    files_failed: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    total_errors: int = 0
    scan_time_ms: float = 0.0
    parsers_used: Set[str] = field(default_factory=set)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "files_scanned": self.files_scanned,
            "files_skipped": self.files_skipped,
            "files_unchanged": self.files_unchanged,
            "files_failed": self.files_failed,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "total_errors": self.total_errors,
            "scan_time_ms": self.scan_time_ms,
            "parsers_used": list(self.parsers_used),
        }


class ParserRegistry:
    """
    Registry for language parsers.
    
    Manages parser registration and lookup by extension.
    Supports both direct registration and entry point discovery.
    """

    def __init__(self):
        self._parsers: Dict[str, LanguageParser] = {}
        self._extension_map: Dict[str, str] = {}
        self._parser_factories: Dict[str, Type[LanguageParser]] = {}
        self._logger = logging.getLogger(f"{__name__}.ParserRegistry")

    def register(self, parser: LanguageParser) -> None:
        """
        Register a parser instance.
        
        Args:
            parser: Parser instance to register
            
        Raises:
            ValueError: If parser name is already registered
        """
        name = parser.name

        if name in self._parsers:
            self._logger.warning(f"Overwriting existing parser: {name}")

        self._parsers[name] = parser

        for ext in parser.extensions:
            ext_lower = ext.lower()
            if ext_lower in self._extension_map:
                existing = self._extension_map[ext_lower]
                self._logger.warning(
                    f"Extension {ext} already mapped to {existing}, "
                    f"now mapping to {name}"
                )
            self._extension_map[ext_lower] = name

        self._logger.debug(
            f"Registered parser: {name} for extensions {parser.extensions}"
        )

    def register_factory(
        self,
        name: str,
        factory: Type[LanguageParser],
    ) -> None:
        """
        Register a parser factory (class) for lazy instantiation.
        
        Args:
            name: Parser name
            factory: Parser class
        """
        self._parser_factories[name] = factory
        self._logger.debug(f"Registered parser factory: {name}")

    def unregister(self, name: str) -> bool:
        """
        Unregister a parser by name.
        
        Args:
            name: Parser name to remove
            
        Returns:
            True if parser was removed, False if not found
        """
        if name not in self._parsers:
            return False

        parser = self._parsers.pop(name)

        # Remove extension mappings
        for ext in parser.extensions:
            ext_lower = ext.lower()
            if self._extension_map.get(ext_lower) == name:
                del self._extension_map[ext_lower]

        return True

    def get_parser(self, name: str) -> LanguageParser | None:
        """
        Get a parser by name.
        
        Args:
            name: Parser name
            
        Returns:
            Parser instance or None if not found
        """
        # Try direct lookup first
        if name in self._parsers:
            return self._parsers[name]

        # Try factory instantiation
        if name in self._parser_factories:
            parser = self._parser_factories[name]()
            self.register(parser)
            return parser

        return None

    def get_parser_for_extension(self, extension: str) -> LanguageParser | None:
        """
        Get the parser registered for a file extension.
        
        Args:
            extension: File extension (with or without leading dot)
            
        Returns:
            Parser instance or None if no parser handles this extension
        """
        ext = extension if extension.startswith(".") else f".{extension}"
        ext_lower = ext.lower()

        parser_name = self._extension_map.get(ext_lower)
        if parser_name:
            return self.get_parser(parser_name)

        return None

    def get_parser_for_file(self, file_path: Path) -> LanguageParser | None:
        """
        Get the appropriate parser for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Parser instance or None if no parser handles this file
        """
        return self.get_parser_for_extension(file_path.suffix)

    @property
    def registered_parsers(self) -> List[str]:
        """Get list of registered parser names."""
        return list(self._parsers.keys())

    @property
    def supported_extensions(self) -> List[str]:
        """Get list of all supported file extensions."""
        return list(self._extension_map.keys())

    def discover_parsers(self, entry_point_group: str = "jnkn.parsers") -> int:
        """
        Auto-discover parsers via entry points.
        
        Args:
            entry_point_group: Entry point group name to search
            
        Returns:
            Number of parsers discovered
        """
        discovered = 0

        try:
            if sys.version_info >= (3, 10):
                from importlib.metadata import entry_points
                eps = entry_points(group=entry_point_group)
            else:
                from importlib.metadata import entry_points
                all_eps = entry_points()
                eps = all_eps.get(entry_point_group, [])

            for ep in eps:
                try:
                    parser_class = ep.load()
                    if isinstance(parser_class, type) and issubclass(parser_class, LanguageParser):
                        self.register_factory(ep.name, parser_class)
                        discovered += 1
                        self._logger.info(f"Discovered parser via entry point: {ep.name}")
                except Exception as e:
                    self._logger.error(f"Failed to load parser entry point {ep.name}: {e}")

        except Exception as e:
            self._logger.warning(f"Entry point discovery failed: {e}")

        return discovered

    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        return {
            "registered_parsers": len(self._parsers),
            "registered_factories": len(self._parser_factories),
            "supported_extensions": len(self._extension_map),
            "parsers": self.registered_parsers,
            "extensions": self.supported_extensions,
        }


class ParserEngine:
    """
    Central orchestrator for parsing operations.
    
    Manages parser registration, routes files to appropriate parsers,
    and aggregates results.
    
    Usage:
        engine = ParserEngine()
        
        # Register parsers
        engine.register(PythonParser())
        engine.register(TerraformParser())
        
        # Parse single file
        for node_or_edge in engine.parse_file(Path("app.py")):
            process(node_or_edge)
        
        # Scan entire directory
        for result in engine.scan(Path("./src")):
            print(f"Parsed {result.file_path}: {len(result.nodes)} nodes")
    """

    def __init__(self, context: ParserContext | None = None):
        """
        Initialize the parser engine.
        
        Args:
            context: Optional runtime context for all parsers
        """
        self._context = context or ParserContext()
        self._registry = ParserRegistry()
        self._file_hashes: Dict[str, str] = {}  # For incremental scanning
        self._logger = logging.getLogger(f"{__name__}.ParserEngine")

    @property
    def context(self) -> ParserContext:
        """Get the engine's runtime context."""
        return self._context

    @context.setter
    def context(self, value: ParserContext) -> None:
        """Set the engine's runtime context."""
        self._context = value
        # Update all registered parsers
        for parser in self._registry._parsers.values():
            parser.context = value

    @property
    def registry(self) -> ParserRegistry:
        """Get the parser registry."""
        return self._registry

    def register(self, parser: LanguageParser) -> None:
        """
        Register a parser.
        
        Args:
            parser: Parser instance to register
        """
        parser.context = self._context
        self._registry.register(parser)

    def supports(self, file_path: Path) -> bool:
        """
        Check if a file type is supported.
        
        Args:
            file_path: Path to the file
            
        Returns:
            True if a parser exists for this file type
        """
        return self._registry.get_parser_for_file(file_path) is not None

    def get_parser(self, file_path: Path) -> LanguageParser | None:
        """
        Get the parser for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Parser instance or None
        """
        return self._registry.get_parser_for_file(file_path)

    def parse_file(
        self,
        file_path: Path,
        content: bytes | None = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a file and yield nodes and edges.
        
        Args:
            file_path: Path to the file
            content: Optional pre-loaded content
            
        Yields:
            Node or Edge objects
        """
        parser = self._registry.get_parser_for_file(file_path)
        if not parser:
            self._logger.debug(f"No parser for file: {file_path}")
            return

        if content is None:
            try:
                content = file_path.read_bytes()
            except Exception as e:
                self._logger.error(f"Failed to read file {file_path}: {e}")
                return

        try:
            yield from parser.parse(file_path, content)
        except Exception:
            self._logger.exception(f"Parser error for {file_path}")

    def parse_file_full(
        self,
        file_path: Path,
        content: bytes | None = None,
    ) -> ParseResult:
        """
        Parse a file and return complete ParseResult.
        
        Args:
            file_path: Path to the file
            content: Optional pre-loaded content
            
        Returns:
            ParseResult with all nodes, edges, and errors
        """
        parser = self._registry.get_parser_for_file(file_path)
        if not parser:
            return ParseResult(
                file_path=file_path,
                errors=[ParseError(
                    file_path=str(file_path),
                    message=f"No parser registered for extension: {file_path.suffix}",
                    error_type="no_parser",
                    recoverable=True,
                )],
            )

        return parser.parse_full(file_path, content)

    def discover_files(
        self,
        config: ScanConfig,
    ) -> Generator[Path, None, None]:
        """
        Discover files to parse in a directory.
        
        Args:
            config: Scan configuration
            
        Yields:
            Paths to files that should be parsed
        """
        root = config.root_dir
        files_found = 0

        def walk_dir(directory: Path) -> Generator[Path, None, None]:
            nonlocal files_found

            try:
                entries = list(directory.iterdir())
            except PermissionError:
                self._logger.warning(f"Permission denied: {directory}")
                return

            for entry in sorted(entries):
                if config.max_files > 0 and files_found >= config.max_files:
                    return

                if entry.is_dir():
                    if entry.name.startswith("."):
                        continue
                    if config.should_skip_dir(entry.name):
                        continue
                    if entry.is_symlink() and not config.follow_symlinks:
                        continue
                    yield from walk_dir(entry)

                elif entry.is_file():
                    if config.should_skip_file(entry):
                        continue

                    # Check extension filter
                    if config.file_extensions:
                        if entry.suffix.lower() not in config.file_extensions:
                            continue

                    # Check if we have a parser
                    if not self.supports(entry):
                        continue

                    files_found += 1
                    yield entry

        yield from walk_dir(root)

    def scan(
        self,
        config: ScanConfig | None = None,
        progress_callback: Callable[[Path, int, int], None] | None = None,
    ) -> Generator[ParseResult, None, None]:
        """
        Scan a directory and parse all supported files.
        
        Args:
            config: Scan configuration (defaults to current directory)
            progress_callback: Optional callback(file_path, current, total)
            
        Yields:
            ParseResult for each parsed file
        """
        if config is None:
            config = ScanConfig()

        # First, discover all files to get total count
        files = list(self.discover_files(config))
        total = len(files)

        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(file_path, i + 1, total)

            # Check for incremental skip
            if config.incremental:
                try:
                    current_hash = ScanMetadata.compute_hash(str(file_path))
                    cached_hash = self._file_hashes.get(str(file_path))

                    if cached_hash == current_hash:
                        # File unchanged, skip
                        yield ParseResult(
                            file_path=file_path,
                            file_hash=current_hash,
                            metadata={"skipped": "unchanged"},
                        )
                        continue

                    # Update hash cache
                    self._file_hashes[str(file_path)] = current_hash
                except Exception:
                    pass  # Continue with parsing if hash fails

            result = self.parse_file_full(file_path)
            yield result

    def scan_all(
        self,
        config: ScanConfig | None = None,
        progress_callback: Callable[[Path, int, int], None] | None = None,
    ) -> tuple[List[Node], List[Edge], ScanStats]:
        """
        Scan and collect all results.
        
        Convenience method that aggregates all scan results.
        
        Args:
            config: Scan configuration
            progress_callback: Optional progress callback
            
        Returns:
            Tuple of (all_nodes, all_edges, stats)
        """
        start_time = time.perf_counter()
        all_nodes: List[Node] = []
        all_edges: List[Edge] = []
        stats = ScanStats()

        for result in self.scan(config, progress_callback):
            if result.metadata.get("skipped") == "unchanged":
                stats.files_unchanged += 1
                continue

            if result.success:
                all_nodes.extend(result.nodes)
                all_edges.extend(result.edges)
                stats.files_scanned += 1
                stats.total_nodes += len(result.nodes)
                stats.total_edges += len(result.edges)
            else:
                stats.files_failed += 1

            stats.total_errors += len(result.errors)

            # Track which parsers were used
            for cap in result.capabilities_used:
                stats.parsers_used.add(cap.value)

        stats.scan_time_ms = (time.perf_counter() - start_time) * 1000

        return all_nodes, all_edges, stats

    def clear_cache(self) -> None:
        """Clear the incremental scanning cache."""
        self._file_hashes.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "registry": self._registry.get_stats(),
            "cached_files": len(self._file_hashes),
        }


def create_default_engine() -> ParserEngine:
    """
    Create a ParserEngine with default parsers registered.
    
    This is the main factory function for creating a fully-configured
    parser engine with all built-in parsers.
    
    Returns:
        Configured ParserEngine
    """
    engine = ParserEngine()

    # Try to register built-in parsers
    # These may fail if dependencies are missing

    try:
        from .python.parser import PythonParser
        engine.register(PythonParser())
    except ImportError as e:
        logger.debug(f"Python parser not available: {e}")

    try:
        from .terraform.parser import TerraformParser
        engine.register(TerraformParser())
    except ImportError as e:
        logger.debug(f"Terraform parser not available: {e}")

    try:
        from .javascript.parser import JavaScriptParser
        engine.register(JavaScriptParser())
    except ImportError as e:
        logger.debug(f"JavaScript parser not available: {e}")

    try:
        from .kubernetes.parser import KubernetesParser
        engine.register(KubernetesParser())
    except ImportError as e:
        logger.debug(f"Kubernetes parser not available: {e}")

    try:
        from .dbt.manifest_parser import DbtManifestParser
        engine.register(DbtManifestParser())
    except ImportError as e:
        logger.debug(f"dbt parser not available: {e}")

    # Try entry point discovery
    engine.registry.discover_parsers()

    return engine
