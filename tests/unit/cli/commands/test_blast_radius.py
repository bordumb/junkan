"""
Unit tests for the 'blast-radius' command.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner
from jnkn.cli.commands.blast_radius import blast_radius

class TestBlastRadiusCommand:
    """Integration tests for the blast radius CLI."""

    @patch("jnkn.cli.commands.blast_radius._run_with_json")
    @patch("jnkn.cli.commands.blast_radius.format_blast_radius")
    def test_blast_radius_default_output(self, mock_format, mock_run):
        """Test that the text formatter is used by default."""
        runner = CliRunner()
        
        # Mock the analysis result
        mock_result = {
            "source_artifacts": ["env:TEST"],
            "impacted_artifacts": ["file://a.py"]
        }
        mock_run.return_value = mock_result
        mock_format.return_value = "Formatted Output"

        # Mock file existence checks
        with runner.isolated_filesystem():
            # Create the exact default file expected
            jnkn_dir = Path(".jnkn")
            jnkn_dir.mkdir()
            (jnkn_dir / "jnkn.db").touch()
                
            result = runner.invoke(blast_radius, ["env:TEST"])

        assert result.exit_code == 0
        assert "Formatted Output" in result.output
        mock_format.assert_called_once_with(mock_result)

    @patch("jnkn.cli.commands.blast_radius._run_with_json")
    def test_blast_radius_json_output(self, mock_run):
        """Test that --json bypasses the formatter."""
        runner = CliRunner()
        mock_result = {"test": "data"}
        mock_run.return_value = mock_result

        with runner.isolated_filesystem():
            # Explicit file path usage
            with open("graph.json", "w") as f:
                f.write("{}")
            
            result = runner.invoke(blast_radius, ["env:TEST", "--db", "graph.json", "--json"])

        assert result.exit_code == 0
        assert '"test": "data"' in result.output

    @patch("jnkn.cli.commands.blast_radius._run_with_json")
    @patch("jnkn.cli.commands.blast_radius.format_blast_radius")
    def test_blast_radius_fallback_to_json(self, mock_format, mock_run):
        """
        Test that if .jnkn/jnkn.db is missing, it falls back to .jnkn/lineage.json
        automatically.
        """
        runner = CliRunner()
        mock_run.return_value = {"source": [], "impacted": []}
        mock_format.return_value = "OK"

        with runner.isolated_filesystem():
            jnkn_dir = Path(".jnkn")
            jnkn_dir.mkdir()
            # Create ONLY lineage.json, NOT jnkn.db
            lineage_file = jnkn_dir / "lineage.json"
            lineage_file.touch()

            # Run without specifying --db (defaults to .jnkn/jnkn.db)
            result = runner.invoke(blast_radius, ["env:TEST"])

        assert result.exit_code == 0
        # Verify it called the JSON runner, not the SQLite one
        mock_run.assert_called()
        # Verify it passed the fallback path
        args = mock_run.call_args[0]
        assert str(args[0]) == ".jnkn/lineage.json"