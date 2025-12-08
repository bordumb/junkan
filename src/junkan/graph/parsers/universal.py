# junkan/graph/parsers/universal.py
from pathlib import Path
from typing import List, Dict, Any, Optional
from tree_sitter_languages import get_language, get_parser

class UniversalParser:
    EXTENSIONS = {
        ".py": "python", ".go": "go", ".js": "javascript", ".ts": "typescript"
    }
    
    # Tree-sitter queries to extract import names
    QUERIES = {
        "python": """
            (import_from_statement module_name: (dotted_name) @import)
            (import_from_statement module_name: (relative_import) @import)
            (import_statement name: (dotted_name) @import)
        """,
        "javascript": """
            (import_statement source: (string) @import)
        """,
        "typescript": """
            (import_statement source: (string) @import)
        """,
        "go": """
            (import_spec path: (interpreted_string_literal) @import)
        """
    }

    def __init__(self, content: str, file_path: str):
        self.content = content
        self.file_path = Path(file_path)
        self.ext = self.file_path.suffix.lower()
        self.lang = self.EXTENSIONS.get(self.ext)

    def parse(self) -> List[Dict[str, Any]]:
        rels = []
        if not self.lang: return rels
        
        try:
            parser = get_parser(self.lang)
            language = get_language(self.lang)
            tree = parser.parse(bytes(self.content, "utf8"))
            
            query = language.query(self.QUERIES.get(self.lang, ""))
            captures = query.captures(tree.root_node)

            for node, capture_name in captures:
                if capture_name == "import":
                    # 1. Extract raw text (e.g., "junkan.models")
                    raw_import = node.text.decode("utf8").strip("'\"")
                    
                    # 2. Resolve to a likely file path (e.g., "junkan/models.py")
                    upstream = self._resolve(raw_import)
                    
                    rels.append({
                        "upstream": upstream,
                        "metadata": {"raw": raw_import}
                    })
        except Exception as e:
            # Swallow parsing errors for robust scanning
            pass
            
        return rels

    def _resolve(self, raw_import: str) -> str:
        """Simple heuristic to map imports to file paths."""
        if self.lang == "python":
            # Map 'junkan.models' -> 'junkan/models.py'
            return raw_import.replace(".", "/") + ".py"
        return raw_import