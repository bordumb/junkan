"""
Multi-language source code parser.

Uses tree-sitter for accurate, multi-language parsing.
Extracts:
- File nodes
- Import relationships
- Environment variable references (multiple patterns)
- Infrastructure resource definitions
- Configuration references

Supports incremental parsing via file hash tracking.
"""

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Generator, List, Set

try:
    from tree_sitter_languages import get_language, get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False

from ..core.types import Edge, Node, NodeType, RelationshipType, ScanMetadata


@dataclass
class LanguageConfig:
    """Configuration for a language parser."""
    name: str
    tree_sitter_name: str
    extensions: Set[str]
    query_paths: List[Path] = field(default_factory=list)

    def __init__(
        self,
        name: str,
        extensions: List[str],
        query_path: Path | None = None,
        tree_sitter_name: str | None = None,
        query_paths: List[Path] | None = None
    ):
        self.name = name
        self.tree_sitter_name = tree_sitter_name or name
        self.extensions = set(ext.lower() for ext in extensions)
        if query_paths:
            self.query_paths = query_paths
        elif query_path:
            self.query_paths = [query_path]
        else:
            self.query_paths = []


@dataclass
class ParseResult:
    """Result of parsing a single file."""
    file_path: Path
    file_hash: str
    nodes: List[Node]
    edges: List[Edge]
    errors: List[str]


class TreeSitterEngine:
    """
    Multi-language parsing engine using tree-sitter.
    
    Features:
    - Multi-language support via configuration
    - Multiple query files per language
    - Comprehensive env var detection
    - Error resilience
    """

    def __init__(self):
        self._configs: Dict[str, LanguageConfig] = {}
        self._extension_map: Dict[str, str] = {}

    def register_language(self, config: LanguageConfig) -> None:
        """Register a language configuration."""
        self._configs[config.name] = config
        for ext in config.extensions:
            self._extension_map[ext.lower()] = config.name

    def supports(self, file_path: Path) -> str | None:
        """Check if a file is supported."""
        ext = file_path.suffix.lower()
        return self._extension_map.get(ext)

    def parse_file(self, file_path: Path) -> Generator[Node | Edge, None, None]:
        """
        Parse a source file and yield nodes and edges.
        """
        lang_name = self.supports(file_path)
        if not lang_name:
            return

        config = self._configs[lang_name]

        try:
            content = file_path.read_bytes()
            file_hash = ScanMetadata.compute_hash(str(file_path))

            file_id = f"file://{file_path}"
            yield Node(
                id=file_id,
                name=file_path.name,
                type=NodeType.CODE_FILE,
                path=str(file_path),
                language=lang_name,
                file_hash=file_hash,
            )

            if not TREE_SITTER_AVAILABLE:
                return

            parser = get_parser(config.tree_sitter_name)
            tree = parser.parse(content)
            language = get_language(config.tree_sitter_name)

            for query_path in config.query_paths:
                if not query_path.exists():
                    continue

                query_scm = query_path.read_text()
                query = language.query(query_scm)
                captures = query.captures(tree.root_node)

                yield from self._process_captures(
                    captures, file_id, lang_name, str(file_path)
                )

        except Exception as e:
            print(f"⚠️  Error parsing {file_path}: {e}", file=sys.stderr)

    def _process_captures(
        self,
        captures: List,
        file_id: str,
        lang_name: str,
        file_path: str,
    ) -> Generator[Node | Edge, None, None]:
        """Process tree-sitter query captures into nodes and edges."""

        for node, capture_name in captures:
            text = node.text.decode("utf-8")
            clean_text = text.strip('"\'')

            if capture_name == "import":
                target_id = self._resolve_import(clean_text, lang_name)

                yield Node(
                    id=target_id,
                    name=clean_text,
                    type=NodeType.UNKNOWN,
                    metadata={"virtual": True}
                )
                yield Edge(
                    source_id=file_id,
                    target_id=target_id,
                    type=RelationshipType.IMPORTS,
                )

            elif capture_name in ("env_var", "environ_key"):
                env_id = f"env:{clean_text}"

                yield Node(
                    id=env_id,
                    name=clean_text,
                    type=NodeType.ENV_VAR,
                    metadata={"source": capture_name, "file": file_path}
                )
                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                )

            elif capture_name == "res_name":
                infra_id = f"infra:{clean_text}"

                yield Node(
                    id=infra_id,
                    name=clean_text,
                    type=NodeType.INFRA_RESOURCE,
                    path=file_path,
                    metadata={"source": "terraform"}
                )

            elif capture_name == "resource_block":
                infra_id = f"infra:{text}"

                yield Node(
                    id=infra_id,
                    name=text,
                    type=NodeType.INFRA_RESOURCE,
                    path=file_path,
                )

            elif capture_name == "definition":
                entity_id = f"entity:{file_path}:{clean_text}"

                yield Node(
                    id=entity_id,
                    name=clean_text,
                    type=NodeType.CODE_ENTITY,
                    path=file_path,
                    language=lang_name,
                )
                yield Edge(
                    source_id=file_id,
                    target_id=entity_id,
                    type=RelationshipType.CONTAINS,
                )

    def _resolve_import(self, raw_import: str, lang: str) -> str:
        """Resolve raw import string to a file ID."""
        clean = raw_import.strip("'\"")

        if lang == "python":
            if clean.startswith("."):
                return f"file://{clean}"
            return f"file://{clean.replace('.', '/')}.py"

        return f"file://{clean}"

    def parse_file_full(self, file_path: Path) -> ParseResult:
        """Parse a file and return a complete ParseResult."""
        nodes = []
        edges = []
        errors = []

        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception as e:
            file_hash = ""
            errors.append(f"Hash error: {e}")

        try:
            for result in self.parse_file(file_path):
                if isinstance(result, Node):
                    nodes.append(result)
                else:
                    edges.append(result)
        except Exception as e:
            errors.append(f"Parse error: {e}")

        return ParseResult(
            file_path=file_path,
            file_hash=file_hash,
            nodes=nodes,
            edges=edges,
            errors=errors,
        )


def create_default_engine() -> TreeSitterEngine:
    """Create a TreeSitterEngine with default language configurations."""
    engine = TreeSitterEngine()
    base_dir = Path(__file__).resolve().parent

    engine.register_language(LanguageConfig(
        name="python",
        extensions=[".py"],
        query_paths=[
            base_dir / "python/imports.scm",
            base_dir / "python/definitions.scm",
        ]
    ))

    engine.register_language(LanguageConfig(
        name="hcl",
        tree_sitter_name="hcl",
        extensions=[".tf"],
        query_paths=[
            base_dir / "terraform/resources.scm",
        ]
    ))

    return engine
