"""
Unit tests for the Tree-Sitter Query Registry.
"""

from pathlib import Path
from unittest.mock import patch, mock_open
import pytest

from jnkn.parsing.queries import QueryRegistry, QueryPattern

class TestQueryRegistry:
    
    def setup_method(self):
        # Clear registry before each test to ensure isolation
        QueryRegistry._queries = {}

    def test_manual_registration(self):
        pattern = QueryPattern(
            name="test_query",
            language="python",
            query="(identifier) @test",
            captures=("test",)
        )
        
        QueryRegistry.register(pattern)
        
        retrieved = QueryRegistry.get("python", "test_query")
        assert retrieved == pattern
        
        all_py = QueryRegistry.get_all_for_language("python")
        assert len(all_py) == 1
        assert all_py[0] == pattern

    def test_load_from_directory(self, tmp_path):
        """Test loading .scm files from a directory."""
        # Create a dummy .scm file
        query_dir = tmp_path / "queries"
        query_dir.mkdir()
        
        scm_file = query_dir / "imports.scm"
        scm_content = """
        (import_statement) @import
        (call_expression) @func_call
        """
        scm_file.write_text(scm_content)
        
        # Run loader
        count = QueryRegistry.load_from_directory("python", query_dir)
        
        assert count == 1
        
        # Verify registration
        pattern = QueryRegistry.get("python", "imports")
        assert pattern is not None
        assert pattern.query == scm_content
        
        # Verify captures extraction
        # regex r'@(\w+)' should find 'import' and 'func_call'
        assert "import" in pattern.captures
        assert "func_call" in pattern.captures

    def test_load_non_existent_directory(self):
        """Should handle missing directories gracefully."""
        count = QueryRegistry.load_from_directory("python", Path("/non/existent"))
        assert count == 0

    def test_get_unknown_query(self):
        """Should return None for unknown queries."""
        assert QueryRegistry.get("python", "missing") is None
        assert QueryRegistry.get_all_for_language("java") == []