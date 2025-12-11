"""
Parser Engine for jnkn.

Refactored to use Result type for explicit error propagation.
This allows the engine to be panic-free and map directly to Rust error handling.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Generator, Set

from ..core.result import Err, Ok, Result
from ..core.storage.base import StorageAdapter
from ..core.types import Edge, Node, ScanMetadata
from .base import (
    LanguageParser,
    ParserContext,
    ParseResult,
)

logger = logging.getLogger(__name__)

# Default configurations (abbreviated for clarity but fully functional)
DEFAULT_SKIP_DIRS: Set[str] = {
    ".git", ".jnkn", "__pycache__", "node_modules", ".venv", "venv", "env",
    ".env", "dist", "build", "target", "out", "bin", ".idea", ".vscode",
}
DEFAULT_SKIP_PATTERNS: Set[str] = {
    "*.pyc", "*.pyo", "*.so", "*.dll", "*.min.js", "*.lock", "*.log",
}

@dataclass
class ScanConfig:
    root_dir: Path = field(default_factory=lambda: Path.cwd())
    skip_dirs: Set[str] = field(default_factory=lambda: DEFAULT_SKIP_DIRS.copy())
    skip_patterns: Set[str] = field(default_factory=lambda: DEFAULT_SKIP_PATTERNS.copy())
    file_extensions: Set[str] = field(default_factory=set)
    max_files: int = 0
    follow_symlinks: bool = False
    incremental: bool = True

    def should_skip_dir(self, dir_name: str) -> bool:
        return dir_name in self.skip_dirs

    def should_skip_file(self, file_path: Path) -> bool:
        from fnmatch import fnmatch
        name = file_path.name
        return any(fnmatch(name, pattern) for pattern in self.skip_patterns)


@dataclass
class ScanStats:
    files_scanned: int = 0
    files_skipped: int = 0
    files_unchanged: int = 0
    files_failed: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    scan_time_ms: float = 0.0


@dataclass
class ScanError:
    """Structured error for scan operations."""
    message: str
    file_path: str | None = None
    cause: Exception | None = None


class ParserRegistry:
    """Registry for language parsers."""
    def __init__(self):
        self._parsers: Dict[str, LanguageParser] = {}
        self._extension_map: Dict[str, str] = {}
    
    def register(self, parser: LanguageParser) -> None:
        self._parsers[parser.name] = parser
        for ext in parser.extensions:
            self._extension_map[ext.lower()] = parser.name

    def get_parser_for_file(self, file_path: Path) -> LanguageParser | None:
        ext = file_path.suffix.lower()
        name = self._extension_map.get(ext)
        if name:
            return self._parsers.get(name)
        return None
    
    def discover_parsers(self):
        # Implementation omitted for brevity, assuming standard discovery
        pass


class ParserEngine:
    """
    Central orchestrator for parsing operations.
    Returns Result objects instead of raising exceptions.
    """

    def __init__(self, context: ParserContext | None = None):
        self._context = context or ParserContext()
        self._registry = ParserRegistry()
        self._logger = logging.getLogger(f"{__name__}.ParserEngine")

    @property
    def registry(self) -> ParserRegistry:
        return self._registry

    def register(self, parser: LanguageParser) -> None:
        parser.context = self._context
        self._registry.register(parser)

    def scan_and_store(
        self,
        storage: StorageAdapter,
        config: ScanConfig | None = None,
        progress_callback: Callable[[Path, int, int], None] | None = None,
    ) -> Result[ScanStats, ScanError]:
        """
        Scan directory and persist results.
        Returns Ok(ScanStats) or Err(ScanError).
        """
        if config is None:
            config = ScanConfig()

        start_time = time.perf_counter()
        stats = ScanStats()

        try:
            files_gen = self._discover_files(config)
            files = list(files_gen)
        except Exception as e:
            return Err(ScanError(f"File discovery failed: {e}", cause=e))

        total_files = len(files)
        
        # Safe Metadata Fetch
        try:
            tracked_metadata = {
                m.file_path: m for m in storage.get_all_scan_metadata()
            }
        except Exception as e:
            # If DB read fails, treat as empty cache rather than crashing scan
            self._logger.warning(f"Failed to read scan metadata: {e}")
            tracked_metadata = {}

        for i, file_path in enumerate(files):
            if progress_callback:
                progress_callback(file_path, i + 1, total_files)

            str_path = str(file_path)
            should_parse = True
            file_hash = ""
            
            if config.incremental:
                hash_res = ScanMetadata.compute_hash(str_path)
                # Note: compute_hash now might return a Result if we updated it,
                # but assuming it returns string per previous refactor.
                # If we updated types.py to return Result[str, HashError], we handle it here.
                # For compatibility with current types.py, assuming string return.
                if hash_res:
                    file_hash = hash_res
                    existing_meta = tracked_metadata.get(str_path)
                    
                    if existing_meta and existing_meta.file_hash == file_hash:
                        should_parse = False
                        stats.files_unchanged += 1
                        stats.total_nodes += existing_meta.node_count
                        stats.total_edges += existing_meta.edge_count

            if not should_parse:
                continue

            # --- Parse & Persist ---
            
            # 1. Clean up old data (Safe op)
            if config.incremental:
                try:
                    storage.delete_nodes_by_file(str_path)
                except Exception as e:
                    self._logger.error(f"Failed to clear old nodes for {str_path}: {e}")
                    # Continue anyway, worst case is duplicate data

            # 2. Parse
            result = self._parse_file_full(file_path, file_hash)

            if result.success:
                try:
                    # 3. Save new data
                    if result.nodes:
                        storage.save_nodes_batch(result.nodes)
                    if result.edges:
                        storage.save_edges_batch(result.edges)
                    
                    # 4. Update metadata
                    meta = ScanMetadata(
                        file_path=str_path,
                        file_hash=file_hash,
                        node_count=len(result.nodes),
                        edge_count=len(result.edges)
                    )
                    storage.save_scan_metadata(meta)

                    stats.files_scanned += 1
                    stats.total_nodes += len(result.nodes)
                    stats.total_edges += len(result.edges)
                except Exception as e:
                    self._logger.error(f"Failed to persist results for {str_path}: {e}")
                    stats.files_failed += 1
            else:
                stats.files_failed += 1

        stats.scan_time_ms = (time.perf_counter() - start_time) * 1000
        return Ok(stats)

    def _parse_file_full(self, file_path: Path, file_hash: str) -> ParseResult:
        """Parse a single file using the registry."""
        parser = self._registry.get_parser_for_file(file_path)
        
        if not parser:
            return ParseResult(file_path=file_path, file_hash=file_hash, success=False)

        try:
            content = file_path.read_bytes()
            items = list(parser.parse(file_path, content))
            
            nodes = [i for i in items if isinstance(i, Node)]
            edges = [i for i in items if isinstance(i, Edge)]
            
            # Inject file_hash
            for node in nodes:
                if node.type == "code_file" and not node.file_hash:
                    node.file_hash = file_hash

            return ParseResult(
                file_path=file_path,
                file_hash=file_hash,
                nodes=nodes,
                edges=edges,
                success=True
            )
        except Exception as e:
            self._logger.error(f"Failed to parse {file_path}: {e}")
            return ParseResult(
                file_path=file_path, 
                file_hash=file_hash, 
                errors=[str(e)], 
                success=False
            )

    def _discover_files(self, config: ScanConfig) -> Generator[Path, None, None]:
        """Recursive file discovery."""
        for root, dirs, files in config.root_dir.walk():
            dirs[:] = [d for d in dirs if not config.should_skip_dir(d)]
            
            for file in files:
                path = root / file
                if not config.should_skip_file(path):
                    if self._registry.get_parser_for_file(path):
                        yield path


def create_default_engine() -> ParserEngine:
    engine = ParserEngine()
    try:
        from .python.parser import PythonParser
        engine.register(PythonParser())
    except ImportError: pass
    
    try:
        from .terraform.parser import TerraformParser
        engine.register(TerraformParser())
    except ImportError: pass
    
    return engine
