"""
Unit tests for the watch command and watcher logic.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Skip this entire module if watchdog is not installed.
pytest.importorskip("watchdog")

from watchdog.events import FileModifiedEvent, FileDeletedEvent

from jnkn.cli.commands.watch import watch
from jnkn.cli.watcher import ParsingEventHandler, FileSystemWatcher
from jnkn.parsing.base import ParseResult


@pytest.fixture
def mock_components():
    """Fixture to mock core components used by the event handler."""
    engine = MagicMock()
    storage = MagicMock()
    config = MagicMock()
    stitcher = MagicMock()
    return engine, storage, config, stitcher


class TestParsingEventHandler:
    """Tests for the watchdog event handler logic."""

    def test_on_modified_triggers_parse(self, mock_components):
        """Test that modifying a file triggers parsing and storage."""
        engine, storage, config, stitcher = mock_components
        root_dir = Path("/tmp/project")
        
        # Setup mocks
        config.should_skip_dir.return_value = False
        config.should_skip_file.return_value = False
        
        # Mock successful parse
        mock_result = ParseResult(
            file_path=Path("/tmp/project/app.py"),
            file_hash="hash123",
            nodes=[MagicMock()],
            edges=[MagicMock()],
            success=True
        )
        engine._parse_file_full.return_value = mock_result

        handler = ParsingEventHandler(engine, storage, config, stitcher, root_dir)
        
        # Simulate event
        event = FileModifiedEvent("/tmp/project/app.py")
        handler.on_modified(event)

        # Assertions
        engine._parse_file_full.assert_called_once()
        storage.delete_nodes_by_file.assert_called_once_with("/tmp/project/app.py")
        storage.save_nodes_batch.assert_called_once()
        
        # CRITICAL FIX: Parsing saves local edges, and Stitching saves cross-file edges.
        # So we expect this to be called at least once (likely twice).
        assert storage.save_edges_batch.call_count >= 1
        
        storage.save_scan_metadata.assert_called_once()
        
        # Ensure stitching was triggered
        stitcher.stitch.assert_called()

    def test_on_modified_skips_ignored_files(self, mock_components):
        """Test that ignored files do not trigger parsing."""
        engine, storage, config, stitcher = mock_components
        root_dir = Path("/tmp/project")
        
        # Setup config to skip this file
        config.should_skip_file.return_value = True

        handler = ParsingEventHandler(engine, storage, config, stitcher, root_dir)
        
        event = FileModifiedEvent("/tmp/project/ignored.log")
        handler.on_modified(event)

        engine._parse_file_full.assert_not_called()
        storage.save_nodes_batch.assert_not_called()

    def test_on_deleted_cleans_up(self, mock_components):
        """Test that deleting a file removes its data from storage."""
        engine, storage, config, stitcher = mock_components
        root_dir = Path("/tmp/project")

        handler = ParsingEventHandler(engine, storage, config, stitcher, root_dir)
        
        event = FileDeletedEvent("/tmp/project/app.py")
        handler.on_deleted(event)

        storage.delete_nodes_by_file.assert_called_once_with("/tmp/project/app.py")
        storage.delete_scan_metadata.assert_called_once_with("/tmp/project/app.py")
        stitcher.stitch.assert_called()

    def test_parse_failure_handles_gracefully(self, mock_components):
        """Test that parse errors don't crash the handler."""
        engine, storage, config, stitcher = mock_components
        root_dir = Path("/tmp/project")
        
        config.should_skip_file.return_value = False
        
        # Mock failed parse
        mock_result = ParseResult(
            file_path=Path("app.py"),
            file_hash="",
            success=False,
            errors=["Syntax Error"]
        )
        engine._parse_file_full.return_value = mock_result

        handler = ParsingEventHandler(engine, storage, config, stitcher, root_dir)
        event = FileModifiedEvent("/tmp/project/broken.py")
        
        # Should run without raising exception
        handler.on_modified(event)
        
        # Should NOT save anything
        storage.save_nodes_batch.assert_not_called()


class TestWatchCommand:
    """Tests for the CLI watch command."""

    # CRITICAL FIX: Patch the SOURCE of the import (jnkn.cli.watcher), 
    # not the destination (jnkn.cli.commands.watch), because the import is lazy.
    @patch("jnkn.cli.watcher.FileSystemWatcher")
    def test_watch_command_starts_watcher(self, MockWatcher):
        """Test that the CLI command initializes and starts the watcher."""
        runner = CliRunner()
        
        # Mock the watcher instance to verify .start() is called
        mock_instance = MockWatcher.return_value
        
        with runner.isolated_filesystem():
            # Create dummy project
            Path("jnkn.db").touch()
            
            result = runner.invoke(watch, [".", "--db-path", "jnkn.db"])
            
            assert result.exit_code == 0
            assert "Jnkn Auto-Watch" in result.output
            
            # Verify watcher was initialized with correct paths
            args, _ = MockWatcher.call_args
            assert str(args[0]) == str(Path(".").resolve())
            assert str(args[1]) == str(Path("jnkn.db").resolve())
            
            # Verify start was called
            mock_instance.start.assert_called_once()

    @patch("jnkn.cli.watcher.FileSystemWatcher")
    def test_watch_creates_db_dir(self, MockWatcher):
        """Test that the command creates the DB directory if missing."""
        runner = CliRunner()
        
        with runner.isolated_filesystem():
            # Path to a non-existent directory
            db_path = ".jnkn/graph.db"
            
            result = runner.invoke(watch, [".", "--db-path", db_path])
            
            assert result.exit_code == 0
            assert Path(".jnkn").exists()
            assert Path(".jnkn").is_dir()