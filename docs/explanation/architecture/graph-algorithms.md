# Graph Algorithms

Traversal, pathfinding, and analysis algorithms in jnkn.

## Current Design

jnkn's dependency graph is a directed acyclic graph (DAG) stored using NetworkX's `DiGraph` class. The graph supports both in-memory traversal via NetworkX and lazy SQL-based traversal via recursive CTEs for memory efficiency.

### Core Data Structures

The `DependencyGraph` class wraps NetworkX with type-safe operations and secondary indexes:

```python
class DependencyGraph:
    def __init__(self):
        self._graph = nx.DiGraph()                              # NetworkX directed graph
        self._nodes_by_type: Dict[NodeType, Set[str]] = {}     # O(1) type lookups
        self._token_index = TokenIndex()                        # Inverted index for stitching
```

The `TokenIndex` enables fast token-based lookups during stitching:

```python
class TokenIndex:
    def __init__(self):
        self._token_to_nodes: Dict[str, Set[str]] = defaultdict(set)
        self._node_to_tokens: Dict[str, Set[str]] = defaultdict(set)
    
    def find_by_any_token(self, tokens: List[str]) -> Set[str]:
        """Find nodes matching ANY of the given tokens."""
        result = set()
        for token in tokens:
            result.update(self._token_to_nodes.get(token, set()))
        return result
    
    def find_by_all_tokens(self, tokens: List[str]) -> Set[str]:
        """Find nodes matching ALL of the given tokens."""
        if not tokens:
            return set()
        result = self._token_to_nodes.get(tokens[0], set()).copy()
        for token in tokens[1:]:
            result &= self._token_to_nodes.get(token, set())
        return result
```

### Blast Radius (Downstream Impact)

The primary algorithm for impact analysis. Given a changed artifact, find all downstream dependencies that could be affected.

**In-memory traversal** uses NetworkX's built-in descendants:

```python
def get_descendants(self, node_id: str) -> Set[str]:
    """Get all nodes reachable from the given node (O(V+E))."""
    if node_id not in self._graph:
        return set()
    return nx.descendants(self._graph, node_id)
```

**SQL-based traversal** uses recursive CTEs for memory efficiency:

```sql
WITH RECURSIVE descendants AS (
    -- Base case: direct children
    SELECT target_id as id, 1 as depth
    FROM edges WHERE source_id = :node_id
    
    UNION
    
    -- Recursive case: children of children
    SELECT e.target_id, d.depth + 1
    FROM edges e 
    JOIN descendants d ON e.source_id = d.id
    WHERE d.depth < :max_depth  -- Depth limiting
)
SELECT DISTINCT id FROM descendants;
```

**Depth-limited traversal** prevents runaway queries on deeply connected graphs:

```python
def calculate(self, changed_artifacts: List[str], max_depth: int = -1):
    unique_downstream: Set[str] = set()
    for root_id in changed_artifacts:
        descendants = self._get_descendants(root_id, max_depth)
        unique_downstream.update(descendants)
    return self._categorize(unique_downstream)
```

### Upstream Impact (Ancestors)

Find all nodes that depend on a given artifact—useful for understanding "who consumes this?":

```python
def get_ancestors(self, node_id: str) -> Set[str]:
    """Get all nodes that can reach the given node."""
    if node_id not in self._graph:
        return set()
    return nx.ancestors(self._graph, node_id)
```

### Shortest Path (Impact Chain)

Find the shortest path between two nodes to explain *why* a change impacts a downstream artifact:

```python
def get_impact_path(self, source: str, target: str) -> Optional[List[str]]:
    """Find the shortest impact path between source and target."""
    try:
        return nx.shortest_path(self._graph, source=source, target=target)
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return None
```

Example output:
```
infra:payment_db_host → env:DB_HOST → file://services/payment/config.py
```

### Direct Dependencies

Get immediate neighbors without full traversal:

```python
def get_direct_dependencies(self, node_id: str) -> List[Tuple[str, Edge]]:
    """Get direct outgoing edges (what this node depends on)."""
    result = []
    for _, target_id, data in self._graph.out_edges(node_id, data=True):
        edge = data.get("data")
        if edge:
            result.append((target_id, edge))
    return result

def get_direct_dependents(self, node_id: str) -> List[Tuple[str, Edge]]:
    """Get direct incoming edges (what depends on this node)."""
    result = []
    for source_id, _, data in self._graph.in_edges(node_id, data=True):
        edge = data.get("data")
        if edge:
            result.append((source_id, edge))
    return result
```

### Artifact Resolution

The blast radius analyzer attempts multiple ID formats when looking up nodes:

```python
def _get_descendants(self, node_id: str, max_depth: int) -> Set[str]:
    # Try exact ID first
    descendants = self._query_descendants(node_id, max_depth)
    
    if not descendants:
        # Try as file path
        file_id = f"file://{node_id}"
        descendants = self._query_descendants(file_id, max_depth)
    
    if not descendants:
        # Try as env var
        env_id = f"env:{node_id}"
        descendants = self._query_descendants(env_id, max_depth)
    
    if not descendants:
        # Try as infra resource
        infra_id = f"infra:{node_id}"
        descendants = self._query_descendants(infra_id, max_depth)
    
    return descendants
```

### Categorization

Impact results are categorized by node type for clearer reporting:

```python
def _categorize(self, artifacts: Set[str]) -> Dict[str, List[str]]:
    breakdown = {
        "infra": [],   # infra:* nodes
        "data": [],    # table, model, view, topic references
        "code": [],    # file://* nodes
        "env": [],     # env:* nodes
        "unknown": []
    }
    
    for art in artifacts:
        if art.startswith("infra:"):
            breakdown["infra"].append(art)
        elif art.startswith("env:"):
            breakdown["env"].append(art)
        elif art.startswith("file://"):
            breakdown["code"].append(art)
        elif any(x in art for x in ["table", "model", "view", "topic"]):
            breakdown["data"].append(art)
        else:
            breakdown["unknown"].append(art)
    
    return breakdown
```

## Complexity Analysis

| Operation | In-Memory | SQL (CTE) | Notes |
|-----------|-----------|-----------|-------|
| Descendants | O(V+E) | O(V+E) | BFS/DFS traversal |
| Ancestors | O(V+E) | O(V+E) | Reverse BFS |
| Shortest Path | O(V+E) | N/A | BFS-based |
| Direct Neighbors | O(degree) | O(degree) | Single lookup |
| Type Lookup | O(1) | O(n) | Secondary index vs. scan |
| Token Search | O(tokens) | N/A | Inverted index |

## Future Ideas

### Short-term: Confidence-Weighted Traversal

Currently, traversals follow all edges regardless of confidence. Adding confidence thresholds would reduce false positive propagation:

```python
def get_descendants(self, node_id: str, min_confidence: float = 0.0) -> Set[str]:
    """Only follow edges above confidence threshold."""
    visited = set()
    queue = deque([node_id])
    
    while queue:
        current = queue.popleft()
        for _, target, data in self._graph.out_edges(current, data=True):
            edge = data.get("data")
            if edge and edge.confidence >= min_confidence and target not in visited:
                visited.add(target)
                queue.append(target)
    
    return visited
```

### Short-term: Impact Scoring

Weight downstream nodes by their distance and path confidence to prioritize high-impact changes:

```python
def calculate_with_scores(self, changed_artifacts: List[str]) -> Dict[str, float]:
    """Return impact scores (0-1) based on distance and confidence."""
    scores = {}
    for root_id in changed_artifacts:
        for node, distance in nx.single_source_shortest_path_length(self._graph, root_id).items():
            # Score decays with distance
            decay = 1.0 / (1 + distance)
            scores[node] = max(scores.get(node, 0), decay)
    return scores
```

### Medium-term: rustworkx Migration

Replace NetworkX with rustworkx for significant performance improvements:

```python
import rustworkx as rx

class DependencyGraph:
    def __init__(self):
        self._graph = rx.PyDiGraph()
        self._node_id_map: Dict[str, int] = {}  # External ID -> rustworkx index
    
    def get_descendants(self, node_id: str) -> Set[str]:
        idx = self._node_id_map.get(node_id)
        if idx is None:
            return set()
        # 10-100x faster than NetworkX
        descendant_indices = rx.descendants(self._graph, idx)
        return {self._reverse_map[i] for i in descendant_indices}
```

Benchmark expectations based on rustworkx documentation:
- Betweenness centrality: 36,000x faster
- BFS/DFS traversal: 10-50x faster
- Memory usage: 2-5x reduction

### Medium-term: Cycle Detection

Detect circular dependencies that could cause infinite loops or configuration issues:

```python
def find_cycles(self) -> List[List[str]]:
    """Find all strongly connected components (cycles)."""
    try:
        cycles = list(nx.simple_cycles(self._graph))
        return [cycle for cycle in cycles if len(cycle) > 1]
    except nx.NetworkXNoCycle:
        return []
```

### Long-term: Subgraph Extraction

Extract minimal subgraphs for focused analysis or visualization:

```python
def extract_subgraph(self, node_ids: Set[str], include_context: int = 1) -> DependencyGraph:
    """Extract subgraph containing specified nodes plus N hops of context."""
    expanded = set(node_ids)
    for _ in range(include_context):
        for node in list(expanded):
            expanded.update(nx.neighbors(self._graph, node))
            expanded.update(self._graph.predecessors(node))
    
    return self._graph.subgraph(expanded).copy()
```

### Long-term: Parallel Traversal

For very large graphs, parallelize independent traversals:

```python
from concurrent.futures import ThreadPoolExecutor

def calculate_parallel(self, changed_artifacts: List[str]) -> Set[str]:
    """Parallel blast radius calculation for multiple roots."""
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(self._get_descendants, root_id, -1)
            for root_id in changed_artifacts
        ]
        results = set()
        for future in futures:
            results.update(future.result())
        return results
```

### Long-term: Incremental Graph Updates

Currently, the full graph is rebuilt on each scan. Incremental updates would track deltas:

```python
class IncrementalGraph:
    def apply_delta(self, added_nodes: List[Node], removed_nodes: List[str], 
                   added_edges: List[Edge], removed_edges: List[Tuple[str, str]]):
        """Apply incremental changes without full rebuild."""
        for node in removed_nodes:
            self.remove_node(node)
        for edge in removed_edges:
            self.remove_edge(*edge)
        for node in added_nodes:
            self.add_node(node)
        for edge in added_edges:
            self.add_edge(edge)
```