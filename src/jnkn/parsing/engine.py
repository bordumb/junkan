"""
Parser Engine for jnkn.

Refactored to use Result type for explicit error propagation.
This allows the engine to be panic-free and map directly to Rust error handling.
"""

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Generator, List, Set

from ..core.result import Err, Ok, Result
from ..core.storage.base import StorageAdapter
from ..core.types import Edge, Node, ScanMetadata
from .base import (
    LanguageParser,
    ParserContext,
    ParseResult,
)

logger = logging.getLogger(__name__)

# Default configurations
DEFAULT_SKIP_DIRS: Set[str] = {
    ".git",
    ".jnkn",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    ".env",
    "dist",
    "build",
    "target",
    "out",
    "bin",
    ".idea",
    ".vscode",
}
DEFAULT_SKIP_PATTERNS: Set[str] = {
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.min.js",
    "*.lock",
    "*.log",
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
    files_deleted: int = 0
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
        # FIX: Map extension to LIST of parser names to support multiple parsers per ext
        self._extension_map: Dict[str, List[str]] = {}

    def register(self, parser: LanguageParser) -> None:
        self._parsers[parser.name] = parser
        for ext in parser.extensions:
            ext_lower = ext.lower()
            if ext_lower not in self._extension_map:
                self._extension_map[ext_lower] = []
            self._extension_map[ext_lower].append(parser.name)

    def get_parsers_for_file(self, file_path: Path) -> List[LanguageParser]:
        """Get all potential parsers for a file extension."""
        ext = file_path.suffix.lower()
        parser_names = self._extension_map.get(ext, [])
        return [self._parsers[name] for name in parser_names]

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

        # 1. Discover files on disk
        try:
            files_gen = self._discover_files(config)
            files_on_disk = list(files_gen)
        except Exception as e:
            return Err(ScanError(f"File discovery failed: {e}", cause=e))

        total_files = len(files_on_disk)

        # 2. Fetch existing metadata from DB
        try:
            tracked_metadata = {m.file_path: m for m in storage.get_all_scan_metadata()}
        except Exception as e:
            # If DB read fails, treat as empty cache rather than crashing scan
            self._logger.warning(f"Failed to read scan metadata: {e}")
            tracked_metadata = {}

        # 3. Handle Deletions (Pruning)
        disk_paths = set(str(f) for f in files_on_disk)

        if config.incremental:
            for tracked_path in list(tracked_metadata.keys()):
                if tracked_path not in disk_paths:
                    # File was deleted or moved
                    try:
                        self._logger.debug(f"Pruning deleted file: {tracked_path}")
                        storage.delete_nodes_by_file(tracked_path)
                        storage.delete_scan_metadata(tracked_path)
                        stats.files_deleted += 1
                        del tracked_metadata[tracked_path]
                    except Exception as e:
                        self._logger.error(f"Failed to prune {tracked_path}: {e}")

        # 4. Process Files (Add/Update)
        for i, file_path in enumerate(files_on_disk):
            if progress_callback:
                progress_callback(file_path, i + 1, total_files)

            str_path = str(file_path)
            should_parse = True
            file_hash = ""

            if config.incremental:
                hash_res = ScanMetadata.compute_hash(str_path)
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

            # Clean up old data for modified files before re-parsing
            if config.incremental and str_path in tracked_metadata:
                try:
                    storage.delete_nodes_by_file(str_path)
                except Exception as e:
                    self._logger.error(f"Failed to clear old nodes for {str_path}: {e}")

            # Parse
            result = self._parse_file_full(file_path, file_hash)

            if result.success:
                try:
                    # Save new data
                    if result.nodes:
                        storage.save_nodes_batch(result.nodes)
                    if result.edges:
                        storage.save_edges_batch(result.edges)

                    # Update metadata
                    meta = ScanMetadata(
                        file_path=str_path,
                        file_hash=file_hash,
                        node_count=len(result.nodes),
                        edge_count=len(result.edges),
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
        """
        Parse a single file using the best available parser.
        Iterates through all parsers registered for this extension.
        """
        candidate_parsers = self._registry.get_parsers_for_file(file_path)

        if not candidate_parsers:
            return ParseResult(file_path=file_path, file_hash=file_hash, success=False)

        # Try to read content once
        try:
            content = file_path.read_bytes()
        except Exception as e:
            return ParseResult(
                file_path=file_path, file_hash=file_hash, errors=[str(e)], success=False
            )

        # Find the first parser that accepts this file content
        selected_parser = None
        for parser in candidate_parsers:
            if parser.can_parse(file_path, content):
                selected_parser = parser
                break

        if not selected_parser:
            # No parser claimed it (e.g. .yaml file that isn't K8s or Spark)
            return ParseResult(file_path=file_path, file_hash=file_hash, success=False)

        try:
            items = list(selected_parser.parse(file_path, content))

            nodes = [i for i in items if isinstance(i, Node)]
            edges = [i for i in items if isinstance(i, Edge)]

            # Inject file_hash into file nodes
            for node in nodes:
                if node.type == "code_file" and not node.file_hash:
                    node.file_hash = file_hash

            return ParseResult(
                file_path=file_path, file_hash=file_hash, nodes=nodes, edges=edges, success=True
            )
        except Exception as e:
            self._logger.error(f"Failed to parse {file_path} with {selected_parser.name}: {e}")
            return ParseResult(
                file_path=file_path, file_hash=file_hash, errors=[str(e)], success=False
            )

    def _discover_files(self, config: ScanConfig) -> Generator[Path, None, None]:
        """Recursive file discovery."""
        for root, dirs, files in config.root_dir.walk():
            # In-place filtering of directories to prevent recursion into skipped dirs
            dirs[:] = [d for d in dirs if not config.should_skip_dir(d)]

            for file in files:
                path = root / file
                if not config.should_skip_file(path):
                    # Check if ANY registered parser supports this extension
                    if self._registry.get_parsers_for_file(path):
                        yield path


def create_default_engine() -> ParserEngine:
    """Factory to create a ParserEngine with standard parsers registered."""
    engine = ParserEngine()

    # Register parsers (Order doesn't matter for extension mapping now)

    try:
        from .python.parser import PythonParser

        engine.register(PythonParser())
    except ImportError:
        pass

    try:
        from .terraform.parser import TerraformParser

        engine.register(TerraformParser())
    except ImportError:
        pass

    try:
        from .javascript.parser import JavaScriptParser

        engine.register(JavaScriptParser())
    except ImportError:
        pass

    try:
        from .kubernetes.parser import KubernetesParser

        engine.register(KubernetesParser())
    except ImportError:
        pass

    try:
        from .dbt.source_parser import DbtSourceParser

        engine.register(DbtSourceParser())
    except ImportError:
        pass

    try:
        from .dbt.manifest_parser import DbtManifestParser

        engine.register(DbtManifestParser())
    except ImportError:
        pass

    try:
        from .pyspark.parser import PySparkParser

        engine.register(PySparkParser())
    except ImportError:
        pass

    try:
        from .spark_yaml.parser import SparkYamlParser

        engine.register(SparkYamlParser())
    except ImportError:
        pass

    try:
        from .go.parser import GoParser

        engine.register(GoParser())
    except ImportError:
        pass

    try:
        from .java.parser import JavaParser

        engine.register(JavaParser())
    except ImportError:
        pass

    return engine
