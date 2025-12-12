"""
Unit tests for the dbt Source Parser orchestrator.
"""

from pathlib import Path
from jnkn.parsing.dbt.source_parser import DbtSourceParser

class TestDbtSourceParser:
    
    def test_can_parse_heuristics(self):
        parser = DbtSourceParser()
        
        # 1. Directory based
        assert parser.can_parse(Path("models/marts/core/users.sql"))
        assert parser.can_parse(Path("snapshots/snap.sql"))
        assert parser.can_parse(Path("macros/utils.sql"))
        
        # 2. Content based (if outside standard dir)
        content = b"select * from {{ ref('table') }}"
        assert parser.can_parse(Path("custom/query.sql"), content)
        
        # 3. Negatives
        assert not parser.can_parse(Path("scripts/cleanup.sql"))
        assert not parser.can_parse(Path("models/readme.md"))

    def test_parse_delegation(self):
        """Verify it creates the file node and runs extractors."""
        parser = DbtSourceParser()
        
        sql = "select {{ env_var('KEY') }} from table"
        path = Path("models/test.sql")
        
        results = list(parser.parse(path, sql.encode("utf-8")))
        
        # Should have:
        # 1. File Node
        # 2. Env Var Node (from JinjaExtractor)
        # 3. Edge (File -> Env Var)
        
        assert len(results) >= 3
        
        file_node = next(r for r in results if r.type == "code_file")
        assert file_node.id == "file://models/test.sql"
        assert file_node.language == "sql"
        
        env_node = next(r for r in results if r.type == "env_var")
        assert env_node.name == "KEY"