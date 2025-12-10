"""
Unit tests for the 'scan' command.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner

# Import the command to test
from jnkn.cli.commands.scan import (
    _load_parsers,
    _parse_file,
    _save_output,
    scan,
)


class TestScanCommand:
    """Tests for the main scan command execution."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_graph(self):
        """Mock the DependencyGraph class."""
        with patch("jnkn.cli.commands.scan.DependencyGraph") as mock_cls:
            mock_instance = mock_cls.return_value
            # Default healthy stats
            mock_instance.node_count = 10
            mock_instance.edge_count = 5
            mock_instance.to_dict.return_value = {"nodes": [], "edges": []}
            yield mock_instance

    @pytest.fixture
    def mock_stitcher(self):
        """Mock the Stitcher class."""
        with patch("jnkn.cli.commands.scan.Stitcher") as mock_cls:
            mock_instance = mock_cls.return_value
            mock_instance.stitch.return_value = [] # Return empty list of new edges
            yield mock_instance

    @pytest.fixture
    def mock_load_parsers(self):
        """Mock the parser loader."""
        with patch("jnkn.cli.commands.scan._load_parsers") as mock:
            # Return a dict with a dummy parser
            mock_parser = MagicMock()
            mock_parser.can_parse.return_value = True
            mock_parser.parse.return_value = []
            mock.return_value = {"dummy_parser": mock_parser}
            yield mock

    @pytest.fixture
    def mock_parse_file(self):
        """Mock the file parsing helper."""
        with patch("jnkn.cli.commands.scan._parse_file") as mock:
            mock.return_value = ([], [])  # (nodes, edges)
            yield mock

    @pytest.fixture
    def mock_save_output(self):
        """Mock the output saver."""
        with patch("jnkn.cli.commands.scan._save_output") as mock:
            yield mock

    def test_scan_no_parsers_available(self, runner, mock_load_parsers):
        """Test scanning when no parsers are installed/loaded."""
        mock_load_parsers.return_value = {}  # Empty dict

        with runner.isolated_filesystem():
            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "No parsers available" in result.output
        assert "imports failed" in result.output

    def test_scan_successful_execution(
        self, runner, mock_load_parsers, mock_graph, mock_stitcher, mock_parse_file
    ):
        """Test a standard successful scan."""
        # Fix: parse_file must return nodes for stitching to run
        mock_node = MagicMock()
        mock_parse_file.return_value = ([mock_node], [])

        with runner.isolated_filesystem():
            # Create a dummy file to find
            Path("test.py").touch()

            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "Scanning" in result.output
        assert "Stitching cross-domain dependencies" in result.output
        assert "Scan complete" in result.output
        # Verify flow
        mock_load_parsers.assert_called_once()
        mock_parse_file.assert_called()
        mock_stitcher.stitch.assert_called_once()

    def test_scan_low_node_count_warning(
        self, runner, mock_load_parsers, mock_graph, mock_parse_file
    ):
        """Test that finding < 5 nodes triggers the warning."""
        mock_graph.node_count = 3
        
        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        # Should NOT see "Scan complete"
        assert "Scan complete" not in result.output
        # Should see warning from echo_low_node_warning
        assert "Low node count detected" in result.output
        assert "Troubleshooting:" in result.output

    def test_scan_file_discovery_recursive(self, runner, mock_load_parsers, mock_parse_file, mock_graph):
        """Test that scan finds files recursively by default."""
        with runner.isolated_filesystem():
            Path("root.py").touch()
            Path("subdir").mkdir()
            Path("subdir/nested.py").touch()

            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "Files found: 2" in result.output

    def test_scan_file_discovery_non_recursive(self, runner, mock_load_parsers, mock_parse_file, mock_graph):
        """Test that --no-recursive limits discovery."""
        with runner.isolated_filesystem():
            Path("root.py").touch()
            Path("subdir").mkdir()
            Path("subdir/nested.py").touch()

            result = runner.invoke(scan, [".", "--no-recursive"])

        assert result.exit_code == 0
        assert "Files found: 1" in result.output

    def test_scan_skip_dirs(self, runner, mock_load_parsers, mock_parse_file, mock_graph):
        """Test that ignored directories are skipped."""
        with runner.isolated_filesystem():
            Path("valid.py").touch()
            
            # Create a skipped directory
            node_modules = Path("node_modules")
            node_modules.mkdir()
            (node_modules / "ignored.js").touch()

            result = runner.invoke(scan, ["."])

        # Should only find valid.py
        assert "Files found: 1" in result.output

    def test_scan_output_file(
        self, runner, mock_load_parsers, mock_graph, mock_parse_file, mock_save_output
    ):
        """Test using the -o flag calls the saver."""
        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, [".", "-o", "report.json"])

        assert result.exit_code == 0
        mock_save_output.assert_called_once()
        args = mock_save_output.call_args[0]
        # Check against the MOCK instance, not the class
        assert args[0] == mock_graph 
        assert args[1].name == "report.json"  # The path

    def test_scan_default_output(
        self, runner, mock_load_parsers, mock_graph, mock_parse_file
    ):
        """Test default JSON saving behavior."""
        with runner.isolated_filesystem():
            Path("test.py").touch()
            result = runner.invoke(scan, ["."])
            
            # Check file creation
            expected_path = Path(".jnkn/lineage.json")
            assert expected_path.exists()
            
            # Verify JSON structure (ignores whitespace differences)
            content = json.loads(expected_path.read_text())
            assert content == {"nodes": [], "edges": []}


class TestHelperFunctions:
    """Tests for the internal helper functions in scan.py."""

    def test_load_parsers_success(self):
        """Test loading available parsers."""
        with patch("importlib.import_module") as mock_import:
            # Setup a mock module that has parser classes
            mock_module = MagicMock()
            # The code calls getattr(module, class_name)
            # We ensure any attribute access returns a MagicMock (acting as the class)
            mock_import.return_value = mock_module
            
            # Patch the context import to avoid AttributeErrors if dependencies missing
            with patch("jnkn.parsing.base.ParserContext"):
                parsers = _load_parsers(Path("."))

        # It tries to load 5 parsers (pyspark, python, spark_yaml, terraform, kubernetes)
        assert len(parsers) == 5

    def test_load_parsers_import_error(self):
        """Test graceful failure when a parser module is missing."""
        # Fix: Patch ParserContext FIRST, then break imports.
        # This prevents the patch(ParserContext) itself from failing due to the broken import system.
        with patch("jnkn.parsing.base.ParserContext"):
            with patch("importlib.import_module", side_effect=ImportError("No module")):
                parsers = _load_parsers(Path("."))
        
        # Should return empty dict, not crash
        assert parsers == {}

    def test_save_output_json(self, tmp_path):
        """Test saving graph as JSON."""
        mock_graph = MagicMock()
        mock_graph.to_dict.return_value = {"graph": True}
        
        output_file = tmp_path / "graph.json"
        
        _save_output(mock_graph, output_file)
        
        content = output_file.read_text()
        assert '"graph": true' in content

    def test_save_output_html(self, tmp_path, capsys):
        """Test saving graph as HTML (currently unsupported warning)."""
        mock_graph = MagicMock()
        output_file = tmp_path / "graph.html"
        
        _save_output(mock_graph, output_file)
        
        captured = capsys.readouterr()
        assert "HTML export from scan is currently limited" in captured.err

    def test_save_output_unknown(self, capsys, tmp_path):
        """Test saving with unknown extension."""
        mock_graph = MagicMock()
        output_file = tmp_path / "graph.xyz"
        
        _save_output(mock_graph, output_file)
        
        captured = capsys.readouterr()
        assert "Unknown format: .xyz" in captured.err


class TestFileParsingLogic:
    """Tests for the _parse_file helper."""

    def test_parse_file_success(self, tmp_path):
        """Test successful file parsing."""
        f = tmp_path / "test.py"
        f.write_text("content")
        
        mock_parser = MagicMock()
        mock_parser.can_parse.return_value = True
        
        # Create dummy classes for isinstance check
        class DummyNode:
            pass
        class DummyEdge:
            pass

        # Setup the parser to return instances of our dummy classes
        n_inst = DummyNode()
        e_inst = DummyEdge()
        mock_parser.parse.return_value = [n_inst, e_inst]
        
        # Patch the scan module to use our dummy classes instead of real Node/Edge
        with patch("jnkn.cli.commands.scan.Node", DummyNode), \
             patch("jnkn.cli.commands.scan.Edge", DummyEdge):
            
            parsers = {"test": mock_parser}
            nodes, edges = _parse_file(f, parsers, verbose=False)

            assert len(nodes) == 1
            assert len(edges) == 1
            assert nodes[0] is n_inst
            assert edges[0] is e_inst

    def test_parse_file_read_error(self, tmp_path):
        """Test handling file read errors."""
        # Directory instead of file will cause read error
        f = tmp_path / "dir"
        f.mkdir()
        
        nodes, edges = _parse_file(f, {}, verbose=False)
        assert nodes == []
        assert edges == []

    def test_parse_file_parser_exception(self, tmp_path, capsys):
        """Test handling exception inside a parser."""
        f = tmp_path / "test.py"
        f.write_text("content")
        
        mock_parser = MagicMock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.side_effect = ValueError("Boom")
        
        parsers = {"test": mock_parser}

        # Run with verbose=True to see error output
        nodes, edges = _parse_file(f, parsers, verbose=True)
        
        assert nodes == []
        captured = capsys.readouterr()
        assert "test error: Boom" in captured.err

    def test_parse_file_verbose_output(self, tmp_path, capsys):
        """Test verbose logging."""
        f = tmp_path / "test.py"
        f.write_text("content")
        
        mock_parser = MagicMock()
        mock_parser.can_parse.return_value = True
        mock_parser.parse.return_value = []
        
        _parse_file(f, {"test": mock_parser}, verbose=True)
        
        captured = capsys.readouterr()
        assert "→ test: test.py" in captured.out