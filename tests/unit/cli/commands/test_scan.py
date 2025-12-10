"""
Unit tests for the 'scan' command.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

# Import the command to test
from jnkn.cli.commands.scan import (
    _load_parsers,
    _parse_file,
    _save_output,
    _to_dict,
    scan,
)


class TestScanCommand:
    """Tests for the main scan command execution."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def mock_graph(self):
        """
        Mock the LineageGraph class.
        PATCH TARGET: jnkn.graph.lineage.LineageGraph
        We patch the source because scan.py uses a local import inside the function.
        """
        with patch("jnkn.graph.lineage.LineageGraph") as mock_cls:
            mock_instance = mock_cls.return_value
            # Default stats to a "healthy" scan to avoid low node warning
            mock_instance.stats.return_value = {"total_nodes": 10, "total_edges": 5}
            mock_instance.to_json.return_value = '{"nodes": [], "edges": []}'
            yield mock_cls

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
        assert "Install with: pip install jnkn[full]" in result.output

    def test_scan_successful_execution(
        self, runner, mock_load_parsers, mock_graph, mock_parse_file
    ):
        """Test a standard successful scan."""
        with runner.isolated_filesystem():
            # Create a dummy file to find
            Path("test.py").touch()

            result = runner.invoke(scan, ["."])

        assert result.exit_code == 0
        assert "Scanning" in result.output
        assert "Scan complete" in result.output
        assert "Nodes: 10" in result.output  # From mock_graph stats

        # Verify flow
        mock_load_parsers.assert_called_once()
        mock_parse_file.assert_called()
        mock_graph.return_value.load_from_dict.assert_called_once()

    def test_scan_low_node_count_warning(
        self, runner, mock_load_parsers, mock_graph, mock_parse_file
    ):
        """Test that finding < 5 nodes triggers the warning."""
        # Set stats to trigger warning
        mock_graph.return_value.stats.return_value = {"total_nodes": 3, "total_edges": 0}

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
            result = runner.invoke(scan, [".", "-o", "report.html"])

        assert result.exit_code == 0
        mock_save_output.assert_called_once()
        args = mock_save_output.call_args[0]
        assert isinstance(args[0], type(mock_graph.return_value))  # The graph
        assert args[1].name == "report.html"  # The path

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
            # Verify it wrote JSON
            assert expected_path.read_text() == '{"nodes": [], "edges": []}'


class TestHelperFunctions:
    """Tests for the internal helper functions in scan.py."""

    def test_load_parsers_success(self):
        """Test loading available parsers."""
        mock_parser_class = MagicMock()
        
        with patch("importlib.import_module") as mock_import:
            # Create a mock module that has the requested parser class
            mock_module = MagicMock()
            
            # Ensure the module object has all attributes
            mock_module.PySparkParser = mock_parser_class
            mock_module.PythonParser = mock_parser_class
            mock_module.SparkYamlParser = mock_parser_class
            mock_module.TerraformParser = mock_parser_class
            
            mock_import.return_value = mock_module

            # PATCH TARGET: jnkn.parsing.base.ParserContext (the actual class)
            with patch("jnkn.parsing.base.ParserContext"):
                parsers = _load_parsers(Path("."))

        assert "python" in parsers
        assert isinstance(parsers["python"], MagicMock)

    def test_load_parsers_import_error(self):
        """Test graceful failure when a parser module is missing."""
        # Patch ParserContext at its source
        with patch("jnkn.parsing.base.ParserContext"):
            with patch("importlib.import_module", side_effect=ImportError("No module")):
                parsers = _load_parsers(Path("."))
        
        # Should return empty dict, not crash
        assert parsers == {}

    def test_to_dict_pydantic(self):
        """Test _to_dict with a Pydantic-like object."""
        mock_obj = MagicMock()
        mock_obj.model_dump.return_value = {"id": "1", "name": "test"}
        # Must remove __dict__ so hasattr(item, "__dict__") doesn't interfere
        del mock_obj.__dict__

        assert _to_dict(mock_obj) == {"id": "1", "name": "test"}

    def test_to_dict_plain_object(self):
        """Test _to_dict with a plain object."""
        class SimpleObj:
            def __init__(self):
                self.x = 1
                self._private = 2
        
        obj = SimpleObj()
        assert _to_dict(obj) == {"x": 1}

    def test_save_output_json(self, tmp_path):
        """Test saving graph as JSON."""
        mock_graph = MagicMock()
        mock_graph.to_json.return_value = '{"graph": true}'
        
        output_file = tmp_path / "graph.json"
        
        _save_output(mock_graph, output_file)
        
        assert output_file.read_text() == '{"graph": true}'

    def test_save_output_html(self, tmp_path):
        """Test saving graph as HTML (export_html called)."""
        mock_graph = MagicMock()
        output_file = tmp_path / "graph.html"
        
        _save_output(mock_graph, output_file)
        
        mock_graph.export_html.assert_called_once_with(output_file)

    def test_save_output_unknown(self, capsys, tmp_path):
        """Test saving with unknown extension."""
        mock_graph = MagicMock()
        output_file = tmp_path / "graph.xyz"
        
        _save_output(mock_graph, output_file)
        
        captured = capsys.readouterr()
        assert "Unknown format: .xyz" in captured.err


class TestFileParsingLogic:
    """Tests for the _parse_file helper."""

    @pytest.fixture
    def mock_parser(self):
        parser = MagicMock()
        parser.can_parse.return_value = True
        return parser

    def test_parse_file_success(self, tmp_path, mock_parser):
        """Test successful file parsing."""
        f = tmp_path / "test.py"
        f.write_text("content")
        
        # Setup parser to return one node and one edge
        
        # Mock Node (no source_id)
        node = MagicMock()
        del node.source_id 
        node.model_dump.return_value = {"id": "n1"}
        
        # Mock Edge (has source_id)
        edge = MagicMock()
        edge.source_id = "n1"
        # Ensure the dictionary returned by model_dump has source_id
        edge.model_dump.return_value = {"source_id": "n1", "target_id": "n2"}
        
        # The parser returns a mix of both
        mock_parser.parse.return_value = [node, edge]
        parsers = {"test": mock_parser}

        nodes, edges = _parse_file(f, parsers, verbose=False)

        # Assertion logic: _parse_file splits them into nodes/edges lists
        assert len(nodes) == 1
        assert len(edges) == 1
        assert nodes[0] == {"id": "n1"}
        assert edges[0] == {"source_id": "n1", "target_id": "n2"}

    def test_parse_file_read_error(self, tmp_path):
        """Test handling file read errors."""
        # Directory instead of file will cause read error
        f = tmp_path / "dir"
        f.mkdir()
        
        nodes, edges = _parse_file(f, {}, verbose=False)
        assert nodes == []
        assert edges == []

    def test_parse_file_parser_exception(self, tmp_path, mock_parser, capsys):
        """Test handling exception inside a parser."""
        f = tmp_path / "test.py"
        f.write_text("content")
        
        mock_parser.parse.side_effect = ValueError("Boom")
        parsers = {"test": mock_parser}

        # Run with verbose=True to see error output
        nodes, edges = _parse_file(f, parsers, verbose=True)
        
        assert nodes == []
        captured = capsys.readouterr()
        assert "test error: Boom" in captured.err

    def test_parse_file_verbose_output(self, tmp_path, mock_parser, capsys):
        """Test verbose logging."""
        f = tmp_path / "test.py"
        f.write_text("content")
        mock_parser.parse.return_value = []
        
        _parse_file(f, {"test": mock_parser}, verbose=True)
        
        captured = capsys.readouterr()
        assert "→ test: test.py" in captured.out