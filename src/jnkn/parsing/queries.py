"""
Tree-Sitter Query Registry.

Centralizes the loading and management of Tree-sitter SCM query files.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class QueryPattern:
    """A named tree-sitter query pattern."""

    name: str
    language: str
    query: str
    captures: Tuple[str, ...]  # Expected capture names


class QueryRegistry:
    """Central registry for tree-sitter queries."""

    _queries: Dict[str, Dict[str, QueryPattern]] = {}  # lang -> name -> pattern

    @classmethod
    def register(cls, pattern: QueryPattern) -> None:
        """Register a new query pattern."""
        if pattern.language not in cls._queries:
            cls._queries[pattern.language] = {}
        cls._queries[pattern.language][pattern.name] = pattern

    @classmethod
    def get(cls, language: str, name: str) -> Optional[QueryPattern]:
        """Retrieve a specific query by language and name."""
        return cls._queries.get(language, {}).get(name)

    @classmethod
    def get_all_for_language(cls, language: str) -> List[QueryPattern]:
        """Retrieve all queries registered for a language."""
        return list(cls._queries.get(language, {}).values())

    @classmethod
    def load_from_directory(cls, lang: str, query_dir: Path) -> int:
        """
        Load all .scm files from a directory and register them.

        Args:
            lang: The language identifier (e.g., 'python', 'javascript')
            query_dir: Path to directory containing .scm files

        Returns:
            Count of queries loaded.
        """
        if not query_dir.exists():
            return 0

        count = 0
        for scm_file in query_dir.glob("*.scm"):
            query_text = scm_file.read_text()
            # Parse captures from query regex (simplified extraction of @name)
            captures = tuple(c for c in re.findall(r"@([a-zA-Z0-9_]+)", query_text))

            cls.register(
                QueryPattern(
                    name=scm_file.stem,
                    language=lang,
                    query=query_text,
                    captures=captures,
                )
            )
            count += 1
        return count


# Auto-register standard query directories on import
base_path = Path(__file__).parent
QueryRegistry.load_from_directory("python", base_path / "python/queries")
QueryRegistry.load_from_directory("javascript", base_path / "javascript/queries")
QueryRegistry.load_from_directory("hcl", base_path / "terraform/queries")
QueryRegistry.load_from_directory("go", base_path / "go/queries")
QueryRegistry.load_from_directory("java", base_path / "java/queries")
