"""
JavaScript/TypeScript Parser for jnkn.

This parser provides comprehensive extraction from JS/TS files:
- Environment variable usage (process.env patterns)
- Import statements (ES modules, CommonJS)
- Function and class definitions
- Framework-specific patterns (Next.js, Vite, etc.)

Supports both JavaScript and TypeScript files with tree-sitter
parsing and regex fallback.

Supported Environment Variable Patterns:
- process.env.VAR
- process.env["VAR"]
- process.env.VAR || "default"
- const { VAR } = process.env
- const { VAR: myVar } = process.env
- import.meta.env.VITE_VAR
- process.env.NEXT_PUBLIC_VAR
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, List, Optional, Set, Union

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)

logger = logging.getLogger(__name__)

# Check if tree-sitter is available
try:
    from tree_sitter_languages import get_language, get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.debug("tree-sitter not available, using regex fallback")


# Tree-sitter query for JavaScript/TypeScript environment variables
ENV_VAR_QUERY = """
; Pattern 1: process.env.VAR_NAME
(member_expression
  object: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  property: (property_identifier) @env_var
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 2: process.env["VAR_NAME"]
(subscript_expression
  object: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  index: (string) @env_var_bracket
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 3: process.env['VAR_NAME'] with template literal
(subscript_expression
  object: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  index: (template_string) @env_var_template
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 4: Destructuring - const { VAR } = process.env
(variable_declarator
  name: (object_pattern
    (shorthand_property_identifier_pattern) @destructured_var)
  value: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 5: Destructuring with rename - const { VAR: myVar } = process.env
(variable_declarator
  name: (object_pattern
    (pair_pattern
      key: (property_identifier) @renamed_var
      value: (identifier)))
  value: (member_expression
    object: (identifier) @_process
    property: (property_identifier) @_env)
  (#eq? @_process "process")
  (#eq? @_env "env"))

; Pattern 6: import.meta.env.VITE_VAR (Vite)
(member_expression
  object: (member_expression
    object: (member_expression
      object: (identifier) @_import
      property: (property_identifier) @_meta)
    property: (property_identifier) @_env)
  property: (property_identifier) @vite_env_var
  (#eq? @_import "import")
  (#eq? @_meta "meta")
  (#eq? @_env "env"))
"""

# Import query
IMPORT_QUERY = """
; ES module import
(import_statement
  source: (string) @import_source)

; Dynamic import
(call_expression
  function: (import)
  arguments: (arguments (string) @dynamic_import))

; CommonJS require
(call_expression
  function: (identifier) @_require
  arguments: (arguments (string) @require_source)
  (#eq? @_require "require"))

; Export from
(export_statement
  source: (string) @export_source)
"""

# Definitions query
DEFINITIONS_QUERY = """
; Function declarations
(function_declaration
  name: (identifier) @function_def)

; Arrow function assignments
(variable_declarator
  name: (identifier) @arrow_function_def
  value: (arrow_function))

; Class declarations
(class_declaration
  name: (identifier) @class_def)

; Method definitions in classes
(method_definition
  name: (property_identifier) @method_def)

; Export function
(export_statement
  declaration: (function_declaration
    name: (identifier) @exported_function))

; Export class
(export_statement
  declaration: (class_declaration
    name: (identifier) @exported_class))
"""


@dataclass
class JSEnvVar:
    """Represents a detected JavaScript environment variable usage."""
    name: str
    pattern: str  # Which pattern detected it
    line: int
    column: int
    is_public: bool = False  # For NEXT_PUBLIC_ or VITE_ prefixes
    framework: Optional[str] = None  # nextjs, vite, etc.

    def to_node_id(self) -> str:
        return f"env:{self.name}"


@dataclass
class JSImport:
    """Represents an import statement."""
    source: str
    is_dynamic: bool
    is_commonjs: bool
    line: int

    def to_file_path(self) -> str:
        """Convert import to a probable file path."""
        source = self.source.strip("'\"")

        # Handle relative imports
        if source.startswith("."):
            return source

        # Handle package imports
        return f"node_modules/{source}"


class JavaScriptParser(LanguageParser):
    """
    Enhanced JavaScript/TypeScript parser with comprehensive env var detection.
    
    Features:
    - Tree-sitter based parsing (with regex fallback)
    - Multiple env var patterns (process.env, import.meta.env)
    - ES module and CommonJS import detection
    - Framework-specific patterns (Next.js, Vite)
    - TypeScript support
    """

    # Regex patterns for fallback parsing
    ENV_VAR_PATTERNS = [
        # process.env.VAR_NAME
        (r'process\.env\.([A-Z][A-Z0-9_]*)', "process.env."),
        # process.env["VAR_NAME"] or process.env['VAR_NAME']
        (r'process\.env\[["\']([^"\']+)["\']\]', "process.env[]"),
        # const { VAR } = process.env
        (r'const\s*\{\s*([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)*)\s*\}\s*=\s*process\.env', "destructuring"),
        # const { VAR: renamed } = process.env
        (r'const\s*\{\s*([A-Z][A-Z0-9_]*)\s*:\s*\w+\s*\}\s*=\s*process\.env', "destructuring_rename"),
        # import.meta.env.VITE_VAR
        (r'import\.meta\.env\.([A-Z][A-Z0-9_]*)', "import.meta.env"),
        # env("VAR_NAME") - dotenv pattern
        (r'env\(["\']([^"\']+)["\']\)', "env()"),
        # process.env.VAR || "default"
        (r'process\.env\.([A-Z][A-Z0-9_]*)\s*\|\|', "process.env_default"),
        # process.env.VAR ?? "default"
        (r'process\.env\.([A-Z][A-Z0-9_]*)\s*\?\?', "process.env_nullish"),
    ]

    IMPORT_PATTERNS = [
        # import x from "module"
        re.compile(r'import\s+.*\s+from\s+["\']([^"\']+)["\']', re.MULTILINE),
        # import "module"
        re.compile(r'import\s+["\']([^"\']+)["\']', re.MULTILINE),
        # require("module")
        re.compile(r'require\s*\(\s*["\']([^"\']+)["\']\s*\)', re.MULTILINE),
        # export * from "module"
        re.compile(r'export\s+.*\s+from\s+["\']([^"\']+)["\']', re.MULTILINE),
    ]

    DEF_PATTERN = re.compile(
        r'^(?:export\s+)?(?:async\s+)?(?:function|class)\s+(\w+)',
        re.MULTILINE
    )

    ARROW_PATTERN = re.compile(
        r'^(?:export\s+)?const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>',
        re.MULTILINE
    )

    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None

    @property
    def name(self) -> str:
        return "javascript"

    @property
    def extensions(self) -> List[str]:
        return [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]

    @property
    def description(self) -> str:
        return "JavaScript/TypeScript parser with comprehensive env var detection"

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.IMPORTS,
            ParserCapability.ENV_VARS,
            ParserCapability.DEFINITIONS,
        ]

    # --- FIX: Implemented abstract method can_parse ---
    def can_parse(self, file_path: Path) -> bool:
        """
        Determine if this parser supports the given file.
        """
        return file_path.suffix.lower() in self.extensions

    def _init_tree_sitter(self, file_path: Path) -> bool:
        """Initialize tree-sitter parser lazily."""
        if not TREE_SITTER_AVAILABLE:
            return False

        # Determine language based on extension
        ext = file_path.suffix.lower()
        if ext in (".ts", ".tsx"):
            lang_name = "typescript"
        else:
            lang_name = "javascript"

        try:
            self._ts_parser = get_parser(lang_name)
            self._ts_language = get_language(lang_name)
            return True
        except Exception as e:
            self._logger.warning(f"Failed to initialize tree-sitter for {lang_name}: {e}")
            return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a JavaScript/TypeScript file and yield nodes and edges.
        """
        from ...core.types import ScanMetadata

        # Determine language
        ext = file_path.suffix.lower()
        if ext in (".ts", ".tsx"):
            language = "typescript"
        else:
            language = "javascript"

        # Create file node
        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception:
            file_hash = ""

        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language=language,
            file_hash=file_hash,
        )

        # Decode content
        try:
            text = content.decode(self._context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                self._logger.error(f"Failed to decode {file_path}: {e}")
                return

        # Try tree-sitter parsing first
        if self._init_tree_sitter(file_path):
            yield from self._parse_with_tree_sitter(file_path, file_id, content, text)
        else:
            yield from self._parse_with_regex(file_path, file_id, text)

    def _parse_with_tree_sitter(
        self,
        file_path: Path,
        file_id: str,
        content: bytes,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Parse using tree-sitter queries."""
        tree = self._ts_parser.parse(content)

        # Parse env vars
        yield from self._extract_env_vars_ts(file_path, file_id, tree, text)

        # Parse imports
        yield from self._extract_imports_ts(file_path, file_id, tree, text)

        # Parse definitions
        yield from self._extract_definitions_ts(file_path, file_id, tree, text)

    def _extract_env_vars_ts(
        self,
        file_path: Path,
        file_id: str,
        tree,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract environment variables using tree-sitter."""
        try:
            query = self._ts_language.query(ENV_VAR_QUERY)
            captures = query.captures(tree.root_node)
        except Exception as e:
            self._logger.debug(f"Tree-sitter env query failed: {e}")
            # Fall back to regex
            yield from self._extract_env_vars_regex(file_path, file_id, text)
            return

        seen_vars: Set[str] = set()

        for node, capture_name in captures:
            # Filter to actual env var captures
            if capture_name not in (
                "env_var", "env_var_bracket", "destructured_var",
                "renamed_var", "vite_env_var",
            ):
                continue

            var_name = node.text.decode("utf-8").strip('"\'')

            if var_name in seen_vars:
                continue
            seen_vars.add(var_name)

            # Determine framework
            framework = self._detect_framework(var_name)
            is_public = var_name.startswith(("NEXT_PUBLIC_", "VITE_", "REACT_APP_"))

            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": capture_name,
                    "file": str(file_path),
                    "line": node.start_point[0] + 1,
                    "column": node.start_point[1],
                    "framework": framework,
                    "is_public": is_public,
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": capture_name},
            )

    def _extract_imports_ts(
        self,
        file_path: Path,
        file_id: str,
        tree,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract imports using tree-sitter."""
        try:
            query = self._ts_language.query(IMPORT_QUERY)
            captures = query.captures(tree.root_node)
        except Exception as e:
            self._logger.debug(f"Tree-sitter import query failed: {e}")
            # Fall back to regex
            yield from self._extract_imports_regex(file_path, file_id, text)
            return

        seen_imports: Set[str] = set()

        for node, capture_name in captures:
            if capture_name not in (
                "import_source", "dynamic_import", "require_source", "export_source"
            ):
                continue

            module_name = node.text.decode("utf-8").strip('"\'')

            if module_name in seen_imports:
                continue
            seen_imports.add(module_name)

            # Determine import type
            is_commonjs = capture_name == "require_source"
            is_dynamic = capture_name == "dynamic_import"

            # Resolve to probable file path
            if module_name.startswith("."):
                target_path = module_name
            else:
                target_path = f"node_modules/{module_name}"

            target_id = f"file://{target_path}"

            yield Node(
                id=target_id,
                name=module_name,
                type=NodeType.UNKNOWN,
                metadata={
                    "virtual": True,
                    "import_name": module_name,
                    "is_commonjs": is_commonjs,
                    "is_dynamic": is_dynamic,
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=target_id,
                type=RelationshipType.IMPORTS,
                metadata={
                    "line": node.start_point[0] + 1,
                    "is_commonjs": is_commonjs,
                    "is_dynamic": is_dynamic,
                },
            )

    def _extract_definitions_ts(
        self,
        file_path: Path,
        file_id: str,
        tree,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract function and class definitions using tree-sitter."""
        try:
            query = self._ts_language.query(DEFINITIONS_QUERY)
            captures = query.captures(tree.root_node)
        except Exception as e:
            self._logger.debug(f"Tree-sitter def query failed: {e}")
            # Fall back to regex
            yield from self._extract_definitions_regex(file_path, file_id, text)
            return

        seen_defs: Set[str] = set()

        for node, capture_name in captures:
            def_name = node.text.decode("utf-8")

            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)

            # Determine type
            if capture_name in ("function_def", "arrow_function_def", "exported_function"):
                entity_type = "function"
            elif capture_name in ("class_def", "exported_class"):
                entity_type = "class"
            elif capture_name == "method_def":
                entity_type = "method"
            else:
                entity_type = "unknown"

            entity_id = f"entity:{file_path}:{def_name}"

            yield Node(
                id=entity_id,
                name=def_name,
                type=NodeType.CODE_ENTITY,
                path=str(file_path),
                language="javascript",
                metadata={
                    "entity_type": entity_type,
                    "line": node.start_point[0] + 1,
                    "is_exported": capture_name.startswith("exported_"),
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )

    def _parse_with_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Fallback parsing using regex patterns."""
        yield from self._extract_env_vars_regex(file_path, file_id, text)
        yield from self._extract_imports_regex(file_path, file_id, text)
        yield from self._extract_definitions_regex(file_path, file_id, text)

    def _extract_env_vars_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract env vars using regex patterns."""
        seen_vars: Set[str] = set()

        for pattern, pattern_name in self.ENV_VAR_PATTERNS:
            regex = re.compile(pattern)

            for match in regex.finditer(text):
                var_names = match.group(1)

                # Handle destructuring (comma-separated)
                if "," in var_names:
                    names = [n.strip() for n in var_names.split(",")]
                else:
                    names = [var_names]

                for var_name in names:
                    if var_name in seen_vars:
                        continue
                    seen_vars.add(var_name)

                    line = text[:match.start()].count('\n') + 1
                    framework = self._detect_framework(var_name)
                    is_public = var_name.startswith(("NEXT_PUBLIC_", "VITE_", "REACT_APP_"))

                    env_id = f"env:{var_name}"

                    yield Node(
                        id=env_id,
                        name=var_name,
                        type=NodeType.ENV_VAR,
                        metadata={
                            "source": pattern_name,
                            "file": str(file_path),
                            "line": line,
                            "framework": framework,
                            "is_public": is_public,
                        },
                    )

                    yield Edge(
                        source_id=file_id,
                        target_id=env_id,
                        type=RelationshipType.READS,
                        metadata={"pattern": pattern_name},
                    )

    def _extract_imports_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract imports using regex patterns."""
        seen_imports: Set[str] = set()

        for pattern in self.IMPORT_PATTERNS:
            for match in pattern.finditer(text):
                module_name = match.group(1)

                if module_name in seen_imports:
                    continue
                seen_imports.add(module_name)

                # Determine import type
                is_commonjs = "require" in match.group(0)

                # Resolve to probable file path
                if module_name.startswith("."):
                    target_path = module_name
                else:
                    target_path = f"node_modules/{module_name}"

                target_id = f"file://{target_path}"

                yield Node(
                    id=target_id,
                    name=module_name,
                    type=NodeType.UNKNOWN,
                    metadata={
                        "virtual": True,
                        "import_name": module_name,
                        "is_commonjs": is_commonjs,
                    },
                )

                yield Edge(
                    source_id=file_id,
                    target_id=target_id,
                    type=RelationshipType.IMPORTS,
                )

    def _extract_definitions_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract definitions using regex patterns."""
        seen_defs: Set[str] = set()

        # Function and class definitions
        for match in self.DEF_PATTERN.finditer(text):
            def_name = match.group(1)

            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)

            entity_id = f"entity:{file_path}:{def_name}"

            yield Node(
                id=entity_id,
                name=def_name,
                type=NodeType.CODE_ENTITY,
                path=str(file_path),
                language="javascript",
                metadata={"entity_type": "function_or_class"},
            )

            yield Edge(
                source_id=file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )

        # Arrow functions
        for match in self.ARROW_PATTERN.finditer(text):
            def_name = match.group(1)

            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)

            entity_id = f"entity:{file_path}:{def_name}"

            yield Node(
                id=entity_id,
                name=def_name,
                type=NodeType.CODE_ENTITY,
                path=str(file_path),
                language="javascript",
                metadata={"entity_type": "arrow_function"},
            )

            yield Edge(
                source_id=file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )

    @staticmethod
    def _detect_framework(var_name: str) -> Optional[str]:
        """Detect framework from env var naming convention."""
        if var_name.startswith("NEXT_PUBLIC_") or var_name.startswith("NEXT_"):
            return "nextjs"
        elif var_name.startswith("VITE_"):
            return "vite"
        elif var_name.startswith("REACT_APP_"):
            return "create-react-app"
        elif var_name.startswith("NUXT_"):
            return "nuxt"
        elif var_name.startswith("GATSBY_"):
            return "gatsby"
        return None


def create_javascript_parser(context: Optional[ParserContext] = None) -> JavaScriptParser:
    """Factory function to create a JavaScript parser."""
    return JavaScriptParser(context)