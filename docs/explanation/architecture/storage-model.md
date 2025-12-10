# Storage Model

SQLite schema and indexing strategy for jnkn's persistence layer.

## Current Design

jnkn uses SQLite as its persistence layer, chosen for zero-configuration portability and single-file deployment. The storage system operates in two modes: an in-memory `MemoryStorage` adapter for testing and CI pipelines, and a persistent `SQLiteStorage` adapter for production use.

### Schema (Version 2)

The database consists of three core tables plus a schema versioning table for migrations:

```sql
-- Schema versioning for migrations
CREATE TABLE schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL,
    description TEXT
);

-- Nodes represent all entities (files, env vars, infra resources, etc.)
CREATE TABLE nodes (
    id TEXT PRIMARY KEY,           -- e.g., "env:DB_HOST", "infra:payment_db"
    name TEXT NOT NULL,            -- Human-readable name
    type TEXT NOT NULL,            -- NodeType enum value
    path TEXT,                     -- File path (if applicable)
    language TEXT,                 -- Source language (python, terraform, etc.)
    file_hash TEXT,                -- For incremental scanning
    tokens TEXT,                   -- JSON array of tokenized name parts
    metadata TEXT,                 -- JSON blob for extensible data
    created_at TEXT NOT NULL
);

-- Edges represent relationships between nodes
CREATE TABLE edges (
    source_id TEXT NOT NULL,
    target_id TEXT NOT NULL,
    type TEXT NOT NULL,            -- RelationshipType enum value
    confidence REAL DEFAULT 1.0,   -- Match confidence score (0.0-1.0)
    match_strategy TEXT,           -- How the match was made
    metadata TEXT,                 -- JSON blob (matched_tokens, explanation)
    created_at TEXT NOT NULL,
    PRIMARY KEY (source_id, target_id, type)
);

-- File scan tracking for incremental updates
CREATE TABLE scan_metadata (
    file_path TEXT PRIMARY KEY,
    file_hash TEXT NOT NULL,       -- Content hash for change detection
    last_scanned TEXT NOT NULL,
    node_count INTEGER DEFAULT 0,
    edge_count INTEGER DEFAULT 0
);
```

### Indexes

Strategic indexes support common query patterns:

```sql
-- Node lookups
CREATE INDEX idx_nodes_type ON nodes(type);    -- Filter by NodeType
CREATE INDEX idx_nodes_path ON nodes(path);    -- File-based queries

-- Edge traversals
CREATE INDEX idx_edges_source ON edges(source_id);    -- Forward traversal
CREATE INDEX idx_edges_target ON edges(target_id);    -- Reverse traversal
CREATE INDEX idx_edges_confidence ON edges(confidence); -- Confidence filtering
```

### Connection Configuration

The SQLite connection uses performance-optimized pragmas:

```python
conn.execute("PRAGMA journal_mode=WAL")      # Write-ahead logging for concurrency
conn.execute("PRAGMA foreign_keys=ON")       # Referential integrity
conn.execute("PRAGMA synchronous=NORMAL")    # Balanced durability/performance
```

### Recursive CTE Traversals

Graph traversals use recursive Common Table Expressions for efficient ancestor/descendant queries without loading the full graph into memory:

```sql
-- Descendants (blast radius calculation)
WITH RECURSIVE descendants AS (
    SELECT target_id as id, 1 as depth
    FROM edges WHERE source_id = ?
    UNION
    SELECT e.target_id, d.depth + 1
    FROM edges e JOIN descendants d ON e.source_id = d.id
    WHERE d.depth < ?  -- Optional depth limit
)
SELECT DISTINCT id FROM descendants;

-- Ancestors (upstream impact)
WITH RECURSIVE ancestors AS (
    SELECT source_id as id, 1 as depth
    FROM edges WHERE target_id = ?
    UNION
    SELECT e.source_id, a.depth + 1
    FROM edges e JOIN ancestors a ON e.target_id = a.id
    WHERE a.depth < ?
)
SELECT DISTINCT id FROM ancestors;
```

### Batch Operations

The storage layer supports batch inserts for 10-100x faster bulk loading:

```python
def save_nodes_batch(self, nodes: List[Node]) -> int:
    with self._connection() as conn:
        conn.executemany("""
            INSERT OR REPLACE INTO nodes 
            (id, name, type, path, language, file_hash, tokens, metadata, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [(n.id, n.name, ...) for n in nodes])
    return len(nodes)
```

### Storage Adapter Interface

Both storage backends implement the `StorageAdapter` abstract base class, enabling seamless switching between in-memory and persistent storage:

```python
class StorageAdapter(ABC):
    @abstractmethod
    def save_node(self, node: Node) -> None: ...
    @abstractmethod
    def load_graph(self) -> DependencyGraph: ...
    @abstractmethod
    def query_descendants(self, node_id: str, max_depth: int) -> List[str]: ...
    # ... additional methods
```

## Scale Characteristics

SQLite performs well for typical project sizes:

| Graph Size | Load Time | Traversal | Notes |
|------------|-----------|-----------|-------|
| <10K nodes | <100ms | <10ms | Excellent |
| 10K-50K nodes | 100-500ms | 10-50ms | Good |
| 50K-100K nodes | 500ms-2s | 50-200ms | Acceptable |
| >100K nodes | >2s | >200ms | Consider alternatives |

The primary bottleneck at scale is not SQLite itself but the in-memory NetworkX graph that gets rebuilt from storage.

## Future Ideas

### Short-term Improvements

**Token Index Persistence**: Currently the inverted token index exists only in memory. Persisting it would eliminate the need to rebuild during graph loading:

```sql
CREATE TABLE token_index (
    token TEXT NOT NULL,
    node_id TEXT NOT NULL,
    PRIMARY KEY (token, node_id)
);
CREATE INDEX idx_token ON token_index(token);
```

**Confidence-based Pruning**: Add a materialized view or summary table for high-confidence edges only, reducing noise in traversals:

```sql
CREATE VIEW high_confidence_edges AS
SELECT * FROM edges WHERE confidence >= 0.7;
```

**Incremental Edge Updates**: Track which edges were created by which stitching rules, enabling targeted re-stitching when rules change.

### Medium-term: rustworkx Integration

Replace NetworkX with rustworkx for 10-100x graph operation speedups while keeping SQLite for persistence. The hybrid architecture would look like:

```
SQLite (persistence) <-> rustworkx (in-memory operations) <-> Python API
```

Key benefits: parallel graph algorithms, better memory layout, native DAG operations.

### Long-term: Graph Database Evaluation

For very large codebases (>100K nodes, >1M edges), evaluate dedicated graph databases:

| Option | Pros | Cons |
|--------|------|------|
| **Memgraph** | In-memory, Cypher-compatible, fast | Requires separate process |
| **DuckDB** | Embedded, analytical queries | Limited graph operations |
| **Kùzu** | Embedded graph DB, Cypher | Newer, smaller ecosystem |
| **Neo4j** | Mature, powerful | Heavy, server-based |

The migration path would maintain the `StorageAdapter` interface, allowing gradual rollout with fallback to SQLite.