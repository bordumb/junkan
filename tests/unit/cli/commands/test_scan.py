"""
Unit tests for the 'scan' command.
Updated to support the Incremental Scanning architecture.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Import core types for mocking returns
from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.core.result import Ok, Err
from jnkn.parsing.engine import ScanStats, ScanError
from jnkn.cli.commands.scan import scan


class TestScanCommand:
    """Tests for the main scan command execution."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_engine(self):
        """Mock the ParserEngine."""
        with patch("jnkn.cli.commands.scan.create_default_engine") as mock_factory:
            engine_instance = mock_factory.return_value
            # Default success response
            stats = ScanStats(
                files_scanned=5,
                files_skipped=0,
                files_unchanged=0,
                files_failed=0,
                total_nodes=10,
                total_edges=5,
                scan_time_ms=100.0
            )
            engine_instance.scan_and_store.return_value = Ok(stats)
            yield engine_instance

    @pytest.fixture
    def mock_storage(self):
        """Mock the SQLiteStorage."""
        with patch("jnkn.cli.commands.scan.SQLiteStorage") as mock_cls:
            storage_instance = mock_cls.return_value
            
            # Mock graph hydration
            mock_graph = MagicMock()
            mock_graph.node_count = 10
            mock_graph.edge_count = 5
            mock_graph.to_dict.return_value = {"nodes": [], "edges": []}
            storage_instance.load_graph.return_value = mock_graph
            
            yield mock_cls

    @pytest.fixture
    def mock_stitcher(self):
        """Mock the Stitcher."""
        with patch("jnkn.cli.commands.scan.Stitcher") as mock_cls:
            stitcher_instance = mock_cls.return_value
            stitcher_instance.stitch.return_value = []  # No new edges by default
            yield stitcher_instance

    def test_scan_successful_execution(
        self, runner, mock_engine, mock_storage, mock_stitcher
    ):
        """Test a standard successful scan."""
        with runner.isolated_filesystem():
            # Create a dummy file to ensure path exists
            Path("test.py").touch()
            
            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "Scanning" in result.output
        assert "Parsed 5 files" in result.output
        assert "Stitching cross-domain dependencies" in result.output
        assert "Scan complete" in result.output
        
        # Verify engine was called
        mock_engine.scan_and_store.assert_called_once()
        
        # Verify storage was initialized and closed
        mock_storage.assert_called()
        mock_storage.return_value.close.assert_called_once()

    def test_scan_force_flag(
        self, runner, mock_engine, mock_storage, mock_stitcher
    ):
        """Test that --force clears storage."""
        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, [".", "--force"])

        assert result.exit_code == 0
        # Verify storage.clear() was called
        mock_storage.return_value.clear.assert_called_once()
        
        # Verify config.incremental was set to False (implied by force logic in scan.py)
        call_args = mock_engine.scan_and_store.call_args
        config = call_args[0][1]  # 2nd arg is config
        assert config.incremental is False

    def test_scan_incremental_message(
        self, runner, mock_engine, mock_storage, mock_stitcher
    ):
        """Test that incremental cache message is shown if DB exists."""
        with runner.isolated_filesystem():
            Path("test.py").touch()
            
            # Simulate existing DB
            db_dir = Path(".jnkn")
            db_dir.mkdir()
            (db_dir / "jnkn.db").touch()
            
            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "Using incremental cache" in result.output

    def test_scan_json_output(
        self, runner, mock_engine, mock_storage, mock_stitcher
    ):
        """Test JSON output format."""
        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, [".", "--json"])

        assert result.exit_code == 0
        
        # Parse output
        data = json.loads(result.output)
        assert data["status"] == "success"
        assert data["data"]["files_parsed"] == 5
        assert data["data"]["nodes_found"] == 10

    def test_scan_engine_failure(
        self, runner, mock_engine, mock_storage
    ):
        """Test handling of parser engine failure."""
        mock_engine.scan_and_store.return_value = Err(ScanError("Engine exploded"))

        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, ["."])

        # Should print error but might not crash depending on implementation
        # The implementation re-raises the error from unwrapping
        assert result.exit_code != 0
        
    def test_scan_low_node_count_warning(
        self, runner, mock_engine, mock_storage, mock_stitcher
    ):
        """Test that low node count triggers warning."""
        # Setup low node count in loaded graph
        mock_graph = mock_storage.return_value.load_graph.return_value
        mock_graph.node_count = 3
        
        # Setup engine to say we scanned files (so warning is valid)
        stats = ScanStats(files_scanned=1, total_nodes=3)
        mock_engine.scan_and_store.return_value = Ok(stats)

        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "Low node count detected" in result.output

    def test_scan_json_export_flag(
        self, runner, mock_engine, mock_storage, mock_stitcher
    ):
        """Test that -o file.json exports the graph as JSON."""
        mock_graph = mock_storage.return_value.load_graph.return_value
        mock_graph.to_dict.return_value = {"nodes": [{"id": "a"}], "edges": []}

        with runner.isolated_filesystem():
            Path("test.py").touch()
            output_file = "graph.json"
            
            result = runner.invoke(scan, [".", "-o", output_file])
            
            assert result.exit_code == 0
            assert Path(output_file).exists()
            content = Path(output_file).read_text()
            assert '"id": "a"' in content