"""
FileSystem Watcher Module.

Implements a real-time file system watcher that triggers incremental
parsing and graph updates. This enables the "Auto-Watch" functionality,
keeping the dependency graph in sync with developer changes without
manual scans.

Key Components:
- FileEventHandler: watchdog handler that filters and dispatches events.
- FileSystemWatcher: Main controller that orchestrates the engine and storage.
"""

import logging
import time
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from jnkn.core.stitching import Stitcher
from jnkn.core.storage.sqlite import SQLiteStorage
from jnkn.parsing.engine import ParserEngine, ScanConfig, create_default_engine

logger = logging.getLogger(__name__)


class ParsingEventHandler(FileSystemEventHandler):
    """
    Handles file system events and triggers parsing logic.

    Filters events based on the scan configuration (skip dirs, file extensions)
    to avoid unnecessary processing overhead.
    """

    def __init__(
        self,
        engine: ParserEngine,
        storage: SQLiteStorage,
        config: ScanConfig,
        stitcher: Stitcher,
        root_dir: Path,
    ):
        """
        Initialize the event handler.

        Args:
            engine: Configured ParserEngine instance.
            storage: Active SQLiteStorage adapter.
            config: Scan configuration for filtering.
            stitcher: Stitcher instance for graph updates.
            root_dir: Root directory of the project.
        """
        self.engine = engine
        self.storage = storage
        self.config = config
        self.stitcher = stitcher
        self.root_dir = root_dir
        self._last_stitch_time = 0.0
        self._cooldown = 0.5  # Seconds between stitches

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if event.is_directory:
            return
        self._process_file(Path(event.src_path))

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if event.is_directory:
            return
        self._process_file(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return
        self._handle_deletion(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        """Handle file move/rename events."""
        if event.is_directory:
            return
        self._handle_deletion(Path(event.src_path))
        self._process_file(Path(event.dest_path))

    def _process_file(self, file_path: Path) -> None:
        """
        Parse a single file and update the graph.

        1. Check if file should be skipped.
        2. Parse file to get nodes and edges.
        3. Persist to storage (upsert).
        4. Trigger partial stitching.
        """
        # Relativize path for consistent filtering checks
        try:
            rel_path = file_path.relative_to(self.root_dir)
        except ValueError:
            # File is outside root (unlikely but possible with symlinks)
            return

        # Check skip logic
        if self._should_skip(rel_path):
            return

        logger.info(f"⚡ Change detected: {rel_path}")

        # We can't use the full engine.scan_and_store because it scans EVERYTHING.
        # We need to target just this file.
        # We access the engine's internal parse logic via _parse_file_full
        # Note: This relies on ParserEngine exposing that method or similar public API.
        # Since we are inside jnkn-core, we can access protected members if needed,
        # but ideally ParserEngine should expose `process_single_file`.
        # Assuming we added `parse_file_full` to ParserEngine public API as per previous dumps.
        
        # Calculate hash for storage consistency
        from jnkn.core.types import ScanMetadata
        
        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception:
            file_hash = ""

        # Use the engine to find the right parser
        result = self.engine._parse_file_full(file_path, file_hash)

        if not result.success:
            if result.errors:
                logger.warning(f"Failed to parse {rel_path}: {result.errors}")
            return

        # Atomic Update: Delete old nodes for this file, then insert new ones
        self.storage.delete_nodes_by_file(str(file_path))
        
        if result.nodes:
            self.storage.save_nodes_batch(result.nodes)
        if result.edges:
            self.storage.save_edges_batch(result.edges)

        # Update metadata
        meta = ScanMetadata(
            file_path=str(file_path),
            file_hash=file_hash,
            node_count=len(result.nodes),
            edge_count=len(result.edges),
        )
        self.storage.save_scan_metadata(meta)

        self._trigger_stitching()

    def _handle_deletion(self, file_path: Path) -> None:
        """Handle file deletion by removing associated nodes."""
        logger.info(f"🗑️  File deleted: {file_path.name}")
        self.storage.delete_nodes_by_file(str(file_path))
        self.storage.delete_scan_metadata(str(file_path))
        self._trigger_stitching()

    def _should_skip(self, rel_path: Path) -> bool:
        """Check against ignore rules."""
        # Check directories
        for part in rel_path.parts[:-1]:
            if self.config.should_skip_dir(part):
                return True
        # Check file
        return self.config.should_skip_file(rel_path)

    def _trigger_stitching(self) -> None:
        """
        Trigger a graph re-stitch.
        
        Debounced to prevent thrashing during rapid saves.
        """
        now = time.time()
        if now - self._last_stitch_time < self._cooldown:
            return

        logger.info("🧵 Re-stitching graph...")
        
        try:
            # Reload fresh graph from DB
            graph = self.storage.load_graph()
            
            # Run stitcher
            new_edges = self.stitcher.stitch(graph)
            
            if new_edges:
                self.storage.save_edges_batch(new_edges)
                logger.info(f"   🔗 {len(new_edges)} new cross-domain links stitched")
            else:
                logger.info("   ✨ Graph stable (No new links needed)")
                
            # Explicit success message
            logger.info("✅ Graph synced.")
            
        except Exception as e:
            logger.error(f"❌ Stitching failed: {e}")
        
        self._last_stitch_time = time.time()


class FileSystemWatcher:
    """
    Main controller for the watch process.
    """

    def __init__(self, root_dir: Path, db_path: Path):
        self.root_dir = root_dir
        self.db_path = db_path
        self.observer: Optional[Observer] = None
        self.storage: Optional[SQLiteStorage] = None

    def start(self) -> None:
        """Start the file watcher loop."""
        logger.info(f"Initializing watcher for {self.root_dir}...")
        logger.info(f"Database: {self.db_path}")

        # Initialize core components
        self.storage = SQLiteStorage(self.db_path)
        engine = create_default_engine()
        stitcher = Stitcher()
        
        # Load standard config defaults
        config = ScanConfig(root_dir=self.root_dir, incremental=True)

        # Setup event handler
        handler = ParsingEventHandler(
            engine=engine,
            storage=self.storage,
            config=config,
            stitcher=stitcher,
            root_dir=self.root_dir
        )

        # Setup Observer
        self.observer = Observer()
        self.observer.schedule(handler, str(self.root_dir), recursive=True)
        self.observer.start()

        logger.info("👀 Jnkn is watching for changes. Press Ctrl+C to stop.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self) -> None:
        """Gracefully stop the watcher."""
        logger.info("Stopping watcher...")
        if self.observer:
            self.observer.stop()
            self.observer.join()
        if self.storage:
            self.storage.close()