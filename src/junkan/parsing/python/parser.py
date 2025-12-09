"""
Enhanced Python Parser for Junkan.

This parser provides comprehensive extraction of Python code artifacts:
- Import statements (standard, from-imports, relative)
- Environment variable usage (multiple patterns)
- Function and class definitions
- Pydantic settings detection
- Various env var libraries (dotenv, dynaconf, environs)

Tree-sitter is used for accurate parsing, with fallback to regex
patterns when tree-sitter is unavailable.

Supported Environment Variable Patterns:
- os.getenv("VAR")
- os.environ.get("VAR")
- os.environ["VAR"]
- getenv("VAR") (after from-import)
- environ.get("VAR") (after from-import)
- Pydantic BaseSettings with Field(env="VAR")
- dotenv_values(".env")["VAR"]
- environs Env().str("VAR")
- dynaconf settings.VAR
"""

from pathlib import Path
from typing import Generator, List, Optional, Dict, Any, Set, Tuple, Union
from dataclasses import dataclass
import re
import logging

from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
    ParseError,
)
from ...core.types import Node, Edge, NodeType, RelationshipType

logger = logging.getLogger(__name__)

# Check if tree-sitter is available
try:
    from tree_sitter_languages import get_parser, get_language
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.debug("tree-sitter not available, using regex fallback")


# Tree-sitter query for Python environment variables
# Note: This covers the main patterns; additional patterns handled in code
ENV_VAR_QUERY = """
; Pattern 1: os.getenv("VAR_NAME")
(call
  function: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @env_var)
  (#eq? @_obj "os")
  (#eq? @_method "getenv"))

; Pattern 2: os.environ.get("VAR_NAME")
(call
  function: (attribute
    object: (attribute
      object: (identifier) @_obj
      attribute: (identifier) @_attr)
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @env_var)
  (#eq? @_obj "os")
  (#eq? @_attr "environ")
  (#eq? @_method "get"))

; Pattern 3: os.environ["VAR_NAME"]
(subscript
  value: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_attr)
  subscript: (string) @environ_key
  (#eq? @_obj "os")
  (#eq? @_attr "environ"))

; Pattern 4: getenv("VAR_NAME") - after from os import getenv
(call
  function: (identifier) @_func
  arguments: (argument_list (string) @getenv_call)
  (#eq? @_func "getenv"))

; Pattern 5: environ.get("VAR_NAME") - after from os import environ
(call
  function: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @environ_get_call)
  (#eq? @_obj "environ")
  (#eq? @_method "get"))

; Pattern 6: environ["VAR_NAME"] - after from os import environ
(subscript
  value: (identifier) @_obj
  subscript: (string) @environ_subscript
  (#eq? @_obj "environ"))

; Pattern 7: env.str("VAR_NAME") / env.int("VAR_NAME") - environs library
(call
  function: (attribute
    object: (identifier) @_env_obj
    attribute: (identifier) @_env_method)
  arguments: (argument_list (string) @environs_var)
  (#match? @_env_obj "^env$")
  (#match? @_env_method "^(str|int|bool|float|list|dict|json|url|path|date|datetime|timedelta)$"))
"""

# Import query
IMPORT_QUERY = """
(import_statement name: (dotted_name) @import)
(import_from_statement module_name: (dotted_name) @from_import)
(import_from_statement module_name: (relative_import) @relative_import)
"""

# Definitions query
DEFINITIONS_QUERY = """
(function_definition
  name: (identifier) @function_def)

(class_definition
  name: (identifier) @class_def)

(decorated_definition
  definition: (function_definition
    name: (identifier) @decorated_function))

(decorated_definition
  definition: (class_definition
    name: (identifier) @decorated_class))
"""

# Pydantic settings query
PYDANTIC_QUERY = """
; Field with env parameter
(call
  function: (identifier) @_field_func
  arguments: (argument_list
    (keyword_argument
      name: (identifier) @_kwarg_name
      value: (string) @pydantic_env_field))
  (#eq? @_field_func "Field")
  (#eq? @_kwarg_name "env"))

; Class inheriting from BaseSettings
(class_definition
  name: (identifier) @settings_class
  superclasses: (argument_list
    (identifier) @_base)
  (#eq? @_base "BaseSettings"))
"""


@dataclass
class PythonEnvVar:
    """Represents a detected environment variable usage."""
    name: str
    pattern: str  # Which pattern detected it
    line: int
    column: int
    default_value: Optional[str] = None
    
    def to_node_id(self) -> str:
        return f"env:{self.name}"


@dataclass
class PythonImport:
    """Represents an import statement."""
    module: str
    is_from_import: bool
    is_relative: bool
    line: int
    names: List[str] = None  # For 'from x import a, b, c'
    
    def to_file_path(self) -> str:
        """Convert import to a probable file path."""
        if self.is_relative:
            return self.module
        return self.module.replace(".", "/") + ".py"


@dataclass
class PythonDefinition:
    """Represents a function or class definition."""
    name: str
    kind: str  # "function" or "class"
    line: int
    decorators: List[str] = None
    
    def to_node_id(self, file_path: str) -> str:
        return f"entity:{file_path}:{self.name}"


class PythonParser(LanguageParser):
    """
    Enhanced Python parser with comprehensive env var detection.
    
    Features:
    - Tree-sitter based parsing (with regex fallback)
    - Multiple env var patterns
    - Import resolution
    - Pydantic settings detection
    - Heuristic detection for env-like assignments
    """
    
    # Regex patterns for fallback parsing
    ENV_VAR_PATTERNS = [
        # os.getenv("VAR") or os.getenv('VAR')
        (r'os\.getenv\s*\(\s*["\']([^"\']+)["\']', "os.getenv"),
        # os.environ.get("VAR")
        (r'os\.environ\.get\s*\(\s*["\']([^"\']+)["\']', "os.environ.get"),
        # os.environ["VAR"]
        (r'os\.environ\s*\[\s*["\']([^"\']+)["\']', "os.environ[]"),
        # getenv("VAR") - after from import
        (r'(?<!os\.)getenv\s*\(\s*["\']([^"\']+)["\']', "getenv"),
        # environ.get("VAR") - after from import
        (r'(?<!os\.)environ\.get\s*\(\s*["\']([^"\']+)["\']', "environ.get"),
        # environ["VAR"] - after from import
        (r'(?<!os\.)environ\s*\[\s*["\']([^"\']+)["\']', "environ[]"),
        # Pydantic Field(env="VAR")
        (r'Field\s*\([^)]*env\s*=\s*["\']([^"\']+)["\']', "pydantic_field"),
        # environs: env.str("VAR"), env.int("VAR"), etc.
        (r'env\.(str|int|bool|float|list|dict|json|url|path)\s*\(\s*["\']([^"\']+)["\']', "environs"),
        # dotenv_values(".env")["VAR"]
        (r'dotenv_values\s*\([^)]*\)\s*\[\s*["\']([^"\']+)["\']', "dotenv_values"),
    ]
    
    IMPORT_PATTERN = re.compile(
        r'^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))',
        re.MULTILINE
    )
    
    DEF_PATTERN = re.compile(
        r'^(?:\s*@[\w.]+(?:\([^)]*\))?\s*\n)*\s*(def|class)\s+(\w+)',
        re.MULTILINE
    )
    
    # Heuristic patterns for env-like variable assignments
    ENV_LIKE_ASSIGNMENT = re.compile(
        r'^(\w+(?:_URL|_HOST|_PORT|_KEY|_SECRET|_TOKEN|_PASSWORD|_USER|_PATH|_DIR|_ENDPOINT|_URI|_DSN|_CONN))\s*=',
        re.MULTILINE | re.IGNORECASE
    )
    
    # Common default values to filter out (false positive prevention)
    COMMON_DEFAULTS = frozenset({
        'localhost', 'true', 'false', 'null', 'none', 'default',
        'dev', 'prod', 'staging', 'test', 'development', 'production',
        'info', 'debug', 'warning', 'error', 'critical',
        'utf-8', 'utf8', 'ascii', 'dev-secret', 'secret',
        'yes', 'no', 'on', 'off', 'enabled', 'disabled',
        'myapp', 'app', 'main', 'root', 'admin', 'user',
    })
    
    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None
    
    @property
    def name(self) -> str:
        return "python"
    
    @property
    def extensions(self) -> List[str]:
        return [".py", ".pyi"]
    
    @property
    def description(self) -> str:
        return "Python parser with comprehensive environment variable detection"
    
    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.IMPORTS,
            ParserCapability.ENV_VARS,
            ParserCapability.DEFINITIONS,
            ParserCapability.CONFIGS,
        ]
    
    def _is_valid_env_var_name(self, name: str) -> bool:
        """
        Validate that a string looks like an environment variable name.
        
        Filters out default values like "5432", "localhost", "dev-secret".
        This prevents false positives from os.getenv("VAR", "default").
        
        Args:
            name: The string to validate
            
        Returns:
            True if it looks like a valid env var name, False otherwise
        """
        # Empty or too short
        if not name or len(name) < 2:
            return False
        
        # Pure digits = port number, timeout, etc.
        if name.isdigit():
            return False
        
        # Known common default values
        if name.lower() in self.COMMON_DEFAULTS:
            return False
        
        # Contains spaces = description or sentence, not env var
        if ' ' in name:
            return False
        
        # Starts with digit = invalid variable name
        if name[0].isdigit():
            return False
        
        # Looks like a path or URL = default value
        if name.startswith(('/', 'http://', 'https://', './', '../', 'redis://', 'postgresql://', 'mysql://')):
            return False
        
        # All lowercase, no separators, long string = probably an English word/default
        # Real env vars are typically UPPER_CASE or have underscores
        if name.islower() and '_' not in name and '-' not in name and len(name) > 6:
            return False
        
        # Looks like a file extension or mime type
        if name.startswith('.') or '/' in name:
            return False
        
        return True
    
    def _init_tree_sitter(self) -> bool:
        """Initialize tree-sitter parser lazily."""
        if self._tree_sitter_initialized:
            return self._ts_parser is not None
        
        self._tree_sitter_initialized = True
        
        if not TREE_SITTER_AVAILABLE:
            return False
        
        try:
            self._ts_parser = get_parser("python")
            self._ts_language = get_language("python")
            return True
        except Exception as e:
            self._logger.warning(f"Failed to initialize tree-sitter: {e}")
            return False
    
    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a Python file and yield nodes and edges.
        
        Args:
            file_path: Path to the Python file
            content: File contents as bytes
            
        Yields:
            Node and Edge objects for discovered entities
        """
        from ...core.types import ScanMetadata
        
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
            language="python",
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
        
        # Track seen env vars across all extraction methods to prevent duplicates
        seen_env_vars: Set[str] = set()
        
        # Try tree-sitter parsing first
        if self._init_tree_sitter():
            for item in self._parse_with_tree_sitter(file_path, file_id, content, text):
                # Track env var names to prevent duplicates
                if hasattr(item, 'type') and item.type == NodeType.ENV_VAR:
                    seen_env_vars.add(item.name)
                yield item
        else:
            for item in self._parse_with_regex(file_path, file_id, text):
                if hasattr(item, 'type') and item.type == NodeType.ENV_VAR:
                    seen_env_vars.add(item.name)
                yield item
        
        # Run heuristic detection for additional coverage (skip already-seen vars)
        yield from self._detect_env_like_assignments(file_path, file_id, text, seen_env_vars)
    
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
        
        # Parse Pydantic settings
        yield from self._extract_pydantic_settings_ts(file_path, file_id, tree, text)
    
    def _extract_env_vars_ts(
        self,
        file_path: Path,
        file_id: str,
        tree,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract environment variables using tree-sitter."""
        query = self._ts_language.query(ENV_VAR_QUERY)
        captures = query.captures(tree.root_node)
        
        seen_vars: Set[str] = set()
        
        for node, capture_name in captures:
            # Filter to actual env var captures
            if capture_name not in (
                "env_var", "environ_key", "getenv_call",
                "environ_get_call", "environ_subscript", "environs_var"
            ):
                continue
            
            var_name = node.text.decode("utf-8").strip('"\'')
            
            # Filter out default values (false positive prevention)
            if not self._is_valid_env_var_name(var_name):
                continue
            
            if var_name in seen_vars:
                continue
            seen_vars.add(var_name)
            
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
        query = self._ts_language.query(IMPORT_QUERY)
        captures = query.captures(tree.root_node)
        
        seen_imports: Set[str] = set()
        
        for node, capture_name in captures:
            module_name = node.text.decode("utf-8")
            
            if module_name in seen_imports:
                continue
            seen_imports.add(module_name)
            
            # Resolve to file path
            if capture_name == "relative_import":
                target_path = module_name
            else:
                target_path = module_name.replace(".", "/") + ".py"
            
            target_id = f"file://{target_path}"
            
            yield Node(
                id=target_id,
                name=module_name,
                type=NodeType.UNKNOWN,  # We don't know if it's a file yet
                metadata={
                    "virtual": True,
                    "import_name": module_name,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=target_id,
                type=RelationshipType.IMPORTS,
                metadata={
                    "line": node.start_point[0] + 1,
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
        query = self._ts_language.query(DEFINITIONS_QUERY)
        captures = query.captures(tree.root_node)
        
        seen_defs: Set[str] = set()
        
        for node, capture_name in captures:
            def_name = node.text.decode("utf-8")
            
            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)
            
            # Determine type
            if capture_name in ("function_def", "decorated_function"):
                entity_type = "function"
            else:
                entity_type = "class"
            
            entity_id = f"entity:{file_path}:{def_name}"
            
            yield Node(
                id=entity_id,
                name=def_name,
                type=NodeType.CODE_ENTITY,
                path=str(file_path),
                language="python",
                metadata={
                    "entity_type": entity_type,
                    "line": node.start_point[0] + 1,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )
    
    def _extract_pydantic_settings_ts(
        self,
        file_path: Path,
        file_id: str,
        tree,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract Pydantic BaseSettings env vars using tree-sitter."""
        query = self._ts_language.query(PYDANTIC_QUERY)
        captures = query.captures(tree.root_node)
        
        seen_vars: Set[str] = set()
        
        # First handle explicit Field(env="VAR") patterns
        for node, capture_name in captures:
            if capture_name == "pydantic_env_field":
                var_name = node.text.decode("utf-8").strip('"\'')
                
                # Apply validation to pydantic fields too
                if not self._is_valid_env_var_name(var_name):
                    continue
                
                if var_name in seen_vars:
                    continue
                seen_vars.add(var_name)
                
                env_id = f"env:{var_name}"
                
                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "pydantic_field",
                        "file": str(file_path),
                        "line": node.start_point[0] + 1,
                    },
                )
                
                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": "pydantic_field"},
                )
        
        # Now detect BaseSettings classes and their fields using regex
        # (more reliable than tree-sitter for this complex pattern)
        yield from self._extract_pydantic_settings_regex(
            file_path, file_id, text, seen_vars
        )
    
    def _extract_pydantic_settings_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Extract Pydantic BaseSettings env vars using regex.
        
        Handles:
        - Classes inheriting from BaseSettings
        - env_prefix in Config inner class
        - Field type annotations
        """
        # Find all BaseSettings subclasses and their bodies
        class_pattern = re.compile(
            r'class\s+(\w+)\s*\([^)]*BaseSettings[^)]*\)\s*:\s*\n(.*?)(?=\nclass\s+\w+\s*[\(:]|\Z)',
            re.DOTALL
        )
        
        for class_match in class_pattern.finditer(text):
            class_name = class_match.group(1)
            class_body = class_match.group(2)
            class_start_line = text[:class_match.start()].count('\n') + 1
            
            # Extract env_prefix from Config class
            prefix = ""
            prefix_match = re.search(
                r'class\s+Config\s*:.*?env_prefix\s*=\s*["\']([^"\']*)["\']',
                class_body,
                re.DOTALL
            )
            if prefix_match:
                prefix = prefix_match.group(1)
            
            # Find all typed field definitions (field_name: type)
            # Match lines like: "    host: str" or "    port: int = Field(...)"
            field_pattern = re.compile(
                r'^([ \t]{4}(\w+)\s*:\s*\w+.*?)$',
                re.MULTILINE
            )
            
            for field_match in field_pattern.finditer(class_body):
                field_line_content = field_match.group(1)
                field_name = field_match.group(2)
                
                # Skip private fields, Config class, and model internals
                if field_name.startswith('_'):
                    continue
                if field_name in ('Config', 'model_config', 'model_fields'):
                    continue
                
                # Check if this field has an explicit env= override in Field()
                # If so, skip auto-generation (the explicit one was already captured)
                explicit_env_match = re.search(
                    r'Field\s*\([^)]*\benv\s*=\s*["\']([^"\']+)["\']',
                    field_line_content
                )
                if explicit_env_match:
                    # Field has explicit env= override, skip auto-generation
                    continue
                
                # Generate env var name: PREFIX + UPPER_CASE(field_name)
                env_var_name = prefix + field_name.upper()
                
                if env_var_name in seen_vars:
                    continue
                seen_vars.add(env_var_name)
                
                # Calculate line number
                field_line = class_start_line + class_body[:field_match.start()].count('\n')
                
                env_id = f"env:{env_var_name}"
                
                yield Node(
                    id=env_id,
                    name=env_var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "pydantic_settings",
                        "file": str(file_path),
                        "line": field_line,
                        "settings_class": class_name,
                        "field_name": field_name,
                        "env_prefix": prefix,
                        "inferred": True,
                    },
                )
                
                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={
                        "pattern": "pydantic_settings",
                        "env_prefix": prefix,
                    },
                )
    
    
    def _parse_with_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Fallback parsing using regex patterns."""
        # Parse env vars
        seen_vars: Set[str] = set()
        
        for pattern, pattern_name in self.ENV_VAR_PATTERNS:
            regex = re.compile(pattern)
            
            for match in regex.finditer(text):
                # environs pattern has group structure different
                if pattern_name == "environs":
                    var_name = match.group(2)
                else:
                    var_name = match.group(1)
                
                # Filter out default values (false positive prevention)
                if not self._is_valid_env_var_name(var_name):
                    continue
                
                if var_name in seen_vars:
                    continue
                seen_vars.add(var_name)
                
                # Calculate line number
                line = text[:match.start()].count('\n') + 1
                
                env_id = f"env:{var_name}"
                
                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": pattern_name,
                        "file": str(file_path),
                        "line": line,
                    },
                )
                
                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": pattern_name},
                )
        
        # Parse imports
        seen_imports: Set[str] = set()
        
        for match in self.IMPORT_PATTERN.finditer(text):
            module_name = match.group(1) or match.group(2)
            
            if module_name in seen_imports:
                continue
            seen_imports.add(module_name)
            
            target_path = module_name.replace(".", "/") + ".py"
            target_id = f"file://{target_path}"
            
            yield Node(
                id=target_id,
                name=module_name,
                type=NodeType.UNKNOWN,
                metadata={"virtual": True},
            )
            
            yield Edge(
                source_id=file_id,
                target_id=target_id,
                type=RelationshipType.IMPORTS,
            )
        
        # Parse definitions
        seen_defs: Set[str] = set()
        
        for match in self.DEF_PATTERN.finditer(text):
            kind = match.group(1)
            def_name = match.group(2)
            
            if def_name in seen_defs:
                continue
            seen_defs.add(def_name)
            
            entity_id = f"entity:{file_path}:{def_name}"
            
            yield Node(
                id=entity_id,
                name=def_name,
                type=NodeType.CODE_ENTITY,
                path=str(file_path),
                language="python",
                metadata={"entity_type": kind},
            )
            
            yield Edge(
                source_id=file_id,
                target_id=entity_id,
                type=RelationshipType.CONTAINS,
            )
    
    def _detect_env_like_assignments(
        self,
        file_path: Path,
        file_id: str,
        text: str,
        seen_env_vars: Optional[Set[str]] = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Heuristic detection of env-like variable assignments.
        
        Looks for patterns like:
            DATABASE_URL = os.getenv(...)
            API_KEY = config.get(...)
        
        This catches assignments that might be sourced from env vars
        even if the exact pattern isn't recognized.
        
        Args:
            seen_env_vars: Set of env var names already detected (to prevent duplicates)
        """
        if seen_env_vars is None:
            seen_env_vars = set()
        
        # Find variable names that look like env vars
        for match in self.ENV_LIKE_ASSIGNMENT.finditer(text):
            var_name = match.group(1).upper()
            
            # Skip if already detected by tree-sitter or regex
            if var_name in seen_env_vars:
                continue
            
            # Get the line content to check if it's actually reading from env
            line_start = text.rfind('\n', 0, match.start()) + 1
            line_end = text.find('\n', match.end())
            if line_end == -1:
                line_end = len(text)
            
            line_content = text[line_start:line_end]
            
            # Check if this looks like an env var read
            env_indicators = [
                'os.getenv', 'os.environ', 'getenv', 'environ',
                'config', 'settings', 'env', 'ENV',
            ]
            
            if not any(ind in line_content for ind in env_indicators):
                continue
            
            line = text[:match.start()].count('\n') + 1
            env_id = f"env:{var_name}"
            
            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "heuristic",
                    "file": str(file_path),
                    "line": line,
                    "confidence": 0.7,  # Lower confidence for heuristic matches
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={
                    "pattern": "heuristic",
                    "confidence": 0.7,
                },
            )


def create_python_parser(context: Optional[ParserContext] = None) -> PythonParser:
    """Factory function to create a Python parser."""
    return PythonParser(context)