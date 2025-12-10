# Extensibility

Plugin architecture for adding new parsers, stitching rules, and storage backends.

## Current Design

jnkn is designed around abstract interfaces that allow extending core functionality without modifying the source code. The three primary extension points are parsers (for new languages/formats), stitching rules (for new relationship types), and storage adapters (for alternative backends).

### Parser Registry

The `ParserRegistry` manages language parsers with support for both direct registration and entry-point discovery:

```python
class ParserRegistry:
    def __init__(self):
        self._parsers: Dict[str, LanguageParser] = {}
        self._extension_map: Dict[str, str] = {}
        self._parser_factories: Dict[str, Type[LanguageParser]] = {}
    
    def register(self, parser: LanguageParser) -> None:
        """Register a parser instance."""
        name = parser.name
        self._parsers[name] = parser
        
        for ext in parser.extensions:
            self._extension_map[ext.lower()] = name
    
    def register_factory(self, name: str, factory: Type[LanguageParser]) -> None:
        """Register a parser class for lazy instantiation."""
        self._parser_factories[name] = factory
    
    def get_parser_for_extension(self, extension: str) -> Optional[LanguageParser]:
        """Get the parser for a file extension."""
        parser_name = self._extension_map.get(extension.lower())
        return self.get_parser(parser_name) if parser_name else None
```

### LanguageParser Abstract Base Class

All parsers implement the `LanguageParser` interface:

```python
from abc import ABC, abstractmethod

class LanguageParser(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique parser identifier (e.g., 'python', 'terraform')."""
        pass
    
    @property
    @abstractmethod
    def extensions(self) -> List[str]:
        """File extensions this parser handles (e.g., ['.py', '.pyw'])."""
        pass
    
    @abstractmethod
    def parse(self, file_path: Path, content: str) -> ParseResult:
        """
        Parse file content and extract nodes/edges.
        
        Args:
            file_path: Path to the file being parsed
            content: File content as string
            
        Returns:
            ParseResult containing discovered nodes and edges
        """
        pass
```

### Creating a Custom Parser

Example: Adding support for a new language (Go):

```python
from jnkn.parsing.base import LanguageParser, ParseResult
from jnkn.core.types import Node, Edge, NodeType

class GoParser(LanguageParser):
    @property
    def name(self) -> str:
        return "go"
    
    @property
    def extensions(self) -> List[str]:
        return [".go"]
    
    def parse(self, file_path: Path, content: str) -> ParseResult:
        result = ParseResult()
        
        # Add file node
        file_node = Node(
            id=f"file://{file_path}",
            name=file_path.name,
            type=NodeType.FILE,
            path=str(file_path),
            language="go"
        )
        result.add_node(file_node)
        
        # Extract environment variables: os.Getenv("VAR_NAME")
        import re
        for match in re.finditer(r'os\.Getenv\(["\'](\w+)["\']\)', content):
            var_name = match.group(1)
            env_node = Node(
                id=f"env:{var_name}",
                name=var_name,
                type=NodeType.ENV_VAR,
                path=str(file_path),
                language="go",
                metadata={"line": content[:match.start()].count('\n') + 1}
            )
            result.add_node(env_node)
            
            # Link file to env var
            result.add_edge(Edge(
                source_id=file_node.id,
                target_id=env_node.id,
                type=RelationshipType.USES
            ))
        
        return result
```

### Entry-Point Discovery

Parsers can be auto-discovered via Python entry points:

```toml
# pyproject.toml
[project.entry-points."jnkn.parsers"]
go = "my_package.parsers:GoParser"
rust = "my_package.parsers:RustParser"
```

The registry discovers these automatically:

```python
def discover_parsers(self, entry_point_group: str = "jnkn.parsers") -> int:
    """Auto-discover parsers via entry points."""
    from importlib.metadata import entry_points
    
    eps = entry_points(group=entry_point_group)
    discovered = 0
    
    for ep in eps:
        parser_class = ep.load()
        if issubclass(parser_class, LanguageParser):
            self.register_factory(ep.name, parser_class)
            discovered += 1
    
    return discovered
```

### StitchingRule Abstract Base Class

Stitching rules discover cross-domain relationships:

```python
from abc import ABC, abstractmethod

class StitchingRule(ABC):
    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()
    
    @abstractmethod
    def get_name(self) -> str:
        """Unique rule identifier."""
        pass
    
    @abstractmethod
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        """
        Apply this rule to discover new edges.
        
        Args:
            graph: The dependency graph to analyze
            
        Returns:
            List of newly discovered edges
        """
        pass
```

### Creating a Custom Stitching Rule

Example: Linking Kubernetes ConfigMap keys to environment variables:

```python
class ConfigMapToEnvRule(StitchingRule):
    def get_name(self) -> str:
        return "ConfigMapToEnvRule"
    
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        edges = []
        
        # Get ConfigMap keys and env vars
        config_keys = graph.get_nodes_by_type(NodeType.CONFIG_KEY)
        env_vars = graph.get_nodes_by_type(NodeType.ENV_VAR)
        
        for config in config_keys:
            for env in env_vars:
                # Check if ConfigMap key matches env var name
                overlap, score = TokenMatcher.significant_token_overlap(
                    config.tokens, env.tokens
                )
                
                if len(overlap) >= 2 and score >= 0.5:
                    edges.append(Edge(
                        source_id=config.id,
                        target_id=env.id,
                        type=RelationshipType.PROVIDES,
                        confidence=score,
                        metadata={
                            "rule": self.get_name(),
                            "matched_tokens": overlap
                        }
                    ))
        
        return edges
```

### StorageAdapter Abstract Base Class

Storage backends implement the `StorageAdapter` interface:

```python
from abc import ABC, abstractmethod

class StorageAdapter(ABC):
    @abstractmethod
    def save_node(self, node: Node) -> None: ...
    
    @abstractmethod
    def save_nodes_batch(self, nodes: List[Node]) -> int: ...
    
    @abstractmethod
    def load_node(self, node_id: str) -> Optional[Node]: ...
    
    @abstractmethod
    def load_all_nodes(self) -> List[Node]: ...
    
    @abstractmethod
    def load_graph(self) -> DependencyGraph: ...
    
    @abstractmethod
    def query_descendants(self, node_id: str, max_depth: int = -1) -> List[str]: ...
    
    @abstractmethod
    def query_ancestors(self, node_id: str, max_depth: int = -1) -> List[str]: ...
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]: ...
    
    @abstractmethod
    def clear(self) -> None: ...
    
    @abstractmethod
    def close(self) -> None: ...
```

### Built-in Storage Adapters

**MemoryStorage**: Fast, ephemeral storage for testing:

```python
class MemoryStorage(StorageAdapter):
    def __init__(self):
        self._nodes: Dict[str, Node] = {}
        self._edges: Dict[str, Edge] = {}
        self._graph = DependencyGraph()
```

**SQLiteStorage**: Persistent storage with schema migrations:

```python
class SQLiteStorage(StorageAdapter):
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()
```

### The Stitcher

The `Stitcher` class orchestrates rule execution:

```python
class Stitcher:
    def __init__(self, config: Optional[MatchConfig] = None):
        self.config = config or MatchConfig()
        self.rules: List[StitchingRule] = [
            EnvVarToInfraRule(self.config),
            InfraToInfraRule(self.config),
        ]
    
    def stitch(self, graph: DependencyGraph) -> List[Edge]:
        """Apply all rules and return discovered edges."""
        all_edges = []
        for rule in self.rules:
            edges = rule.apply(graph)
            all_edges.extend(edges)
            for edge in edges:
                graph.add_edge(edge)
        return all_edges
```

### ParserEngine

The `ParserEngine` orchestrates parsing across files:

```python
class ParserEngine:
    def __init__(self):
        self._registry = ParserRegistry()
    
    def register(self, parser: LanguageParser) -> None:
        self._registry.register(parser)
    
    def parse_file(self, file_path: Path) -> Iterator[Union[Node, Edge]]:
        parser = self._registry.get_parser_for_file(file_path)
        if parser:
            content = file_path.read_text()
            result = parser.parse(file_path, content)
            yield from result.nodes
            yield from result.edges
```

## Current Extension Points Summary

| Extension Point | Interface | Registration |
|-----------------|-----------|--------------|
| Language Parsers | `LanguageParser` | `ParserRegistry.register()` or entry points |
| Stitching Rules | `StitchingRule` | Add to `Stitcher.rules` list |
| Storage Backends | `StorageAdapter` | Pass to analysis components |

## Future Ideas

### Short-term: Rule Entry Points

Enable stitching rules to be discovered via entry points:

```toml
# pyproject.toml
[project.entry-points."jnkn.stitching_rules"]
configmap_env = "my_package.rules:ConfigMapToEnvRule"
helm_values = "my_package.rules:HelmValuesToConfigRule"
```

```python
class RuleRegistry:
    def discover_rules(self, entry_point_group: str = "jnkn.stitching_rules"):
        for ep in entry_points(group=entry_point_group):
            rule_class = ep.load()
            self.register(rule_class())
```

### Short-term: Plugin Configuration

Allow plugins to define their own configuration schema:

```yaml
# .jnkn/config.yaml
plugins:
  go_parser:
    extract_imports: true
    ignore_test_files: false
  
  configmap_rule:
    min_confidence: 0.6
    namespace_aware: true
```

```python
class LanguageParser(ABC):
    @abstractmethod
    def configure(self, config: Dict[str, Any]) -> None:
        """Apply plugin-specific configuration."""
        pass
```

### Medium-term: Hook System

Add lifecycle hooks for custom behavior:

```python
class Hook(ABC):
    @abstractmethod
    def on_scan_start(self, paths: List[Path]) -> None: ...
    
    @abstractmethod
    def on_file_parsed(self, path: Path, result: ParseResult) -> None: ...
    
    @abstractmethod
    def on_stitch_complete(self, edges: List[Edge]) -> None: ...
    
    @abstractmethod
    def on_analysis_complete(self, result: Dict[str, Any]) -> None: ...

class HookRegistry:
    def __init__(self):
        self._hooks: List[Hook] = []
    
    def register(self, hook: Hook) -> None:
        self._hooks.append(hook)
    
    def emit(self, event: str, *args, **kwargs) -> None:
        for hook in self._hooks:
            handler = getattr(hook, event, None)
            if handler:
                handler(*args, **kwargs)
```

### Medium-term: Output Formatters

Pluggable output formats beyond JSON/SARIF/CSV:

```python
class OutputFormatter(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...
    
    @property
    @abstractmethod
    def file_extension(self) -> str: ...
    
    @abstractmethod
    def format(self, result: AnalysisResult) -> str: ...

# Example: Custom HTML report formatter
class HTMLReportFormatter(OutputFormatter):
    @property
    def name(self) -> str:
        return "html_report"
    
    @property
    def file_extension(self) -> str:
        return ".html"
    
    def format(self, result: AnalysisResult) -> str:
        return self._render_template(result)
```

### Long-term: Remote Storage Adapters

Support for distributed graph storage:

```python
class Neo4jStorage(StorageAdapter):
    def __init__(self, uri: str, auth: Tuple[str, str]):
        from neo4j import GraphDatabase
        self._driver = GraphDatabase.driver(uri, auth=auth)
    
    def query_descendants(self, node_id: str, max_depth: int) -> List[str]:
        with self._driver.session() as session:
            result = session.run("""
                MATCH (n {id: $node_id})-[*1..]->(descendant)
                RETURN DISTINCT descendant.id
            """, node_id=node_id)
            return [record["descendant.id"] for record in result]
```

### Long-term: Parser Composition

Allow parsers to delegate to other parsers:

```python
class CompositeParser(LanguageParser):
    def __init__(self, parsers: List[LanguageParser]):
        self._parsers = parsers
    
    def parse(self, file_path: Path, content: str) -> ParseResult:
        combined = ParseResult()
        for parser in self._parsers:
            result = parser.parse(file_path, content)
            combined.merge(result)
        return combined

# Example: Python file with embedded SQL
python_sql_parser = CompositeParser([
    PythonParser(),
    EmbeddedSQLParser()  # Extracts SQL from strings
])
```

### Long-term: Custom Node Types

Allow plugins to define new node types:

```python
# Plugin defines custom type
class CustomNodeType(StrEnum):
    KAFKA_TOPIC = "kafka_topic"
    REDIS_KEY = "redis_key"
    FEATURE_FLAG = "feature_flag"

# Register with core types
NodeTypeRegistry.register(CustomNodeType)

# Now usable in parsers
node = Node(
    id="kafka:user-events",
    name="user-events",
    type=CustomNodeType.KAFKA_TOPIC
)
```