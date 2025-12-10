# Graph Algorithms

Traversal, pathfinding, and analysis algorithms in jnkn.

## Architectural Overview

jnkn's graph engine uses a robust, interface-driven architecture backed by high-performance **rustworkx**. This design decouples analysis logic (Blast Radius, Trace, Diff) from storage and processing, enabling backend agnosticism while leveraging Rust's speed for heavy traversals.

### The IGraph Interface

All graph operations are defined by the `IGraph` protocol, ensuring consistent behavior across different backends (e.g., in-memory `rustworkx`, persistent stores, or test mocks).

```python
class IGraph(Protocol):
    """Abstract contract for dependency graph implementations."""
    
    def get_descendants(self, node_id: str, max_depth: int = -1) -> Set[str]: ...
    def get_ancestors(self, node_id: str, max_depth: int = -1) -> Set[str]: ...
    def get_impacted_nodes(self, source_ids: List[str], max_depth: int = -1) -> Set[str]: ...
    def trace(self, source_id: str, target_id: str) -> List[List[str]]: ...
```

### Core Data Structure: DependencyGraph

The `DependencyGraph` class implements `IGraph` using `rustworkx.PyDiGraph` for speed, with secondary indexes for O(1) lookups.

```python
class DependencyGraph(IGraph):
    def __init__(self):
        self._graph = rx.PyDiGraph()
        # Map external string IDs to internal integer indices
        self._id_to_idx: Dict[str, int] = {}
        self._idx_to_node: Dict[int, Node] = {}
        # Inverted index for fuzzy stitching
        self.token_index = TokenIndex()
```

## Semantic Impact Analysis

Standard graph traversal (downstream/upstream) is insufficient for infrastructure-as-code analysis because dependency direction often opposes data flow direction.

**The Problem:**

  * **Code:** `App.py` --(READS)--\> `ENV_VAR`
  * **Graph Edge:** `App` -\> `Env`
  * **Impact:** If `Env` changes, `App` breaks.
  * **Standard Descendants:** `Env` has *no* outgoing edges to `App`.

**The Solution: `get_impacted_nodes`**
jnkn implements a custom semantic BFS that traverses edges based on their logical data flow, not just graph direction.

```python
def get_impacted_nodes(self, source_ids: List[str], max_depth: int = -1) -> Set[str]:
    """
    Calculate impact by traversing:
    1. Downstream for data flow (PROVIDES, WRITES, FLOWS_TO)
    2. Upstream for dependencies (READS, DEPENDS_ON) - Reverse traversal
    """
    FORWARD_TYPES = {"provides", "writes", "flows_to", "provisions"}
    REVERSE_TYPES = {"reads", "depends_on", "calls"}
    
    # ... BFS implementation that flips direction based on edge type ...
```

This ensures that changing an infrastructure resource correctly "blasts" upwards to the applications that read its outputs.

## Algorithms & Implementations

### 1\. Blast Radius (Semantic BFS)

Finds all artifacts semantically affected by a change.

  * **Algorithm:** Semantic Breadth-First Search (BFS)
  * **Complexity:** $O(V + E)$
  * **Logic:**
      * Start at changed nodes.
      * Follow `PROVIDES` edges forward.
      * Follow `READS` edges backward.
      * Repeat until `max_depth` or exhaust.

### 2\. Lineage Tracing (Pathfinding)

Finds the path explaining *why* Node A affects Node B.

  * **Algorithm:** `rustworkx.all_simple_paths`
  * **Complexity:** $O(V + E)$ (highly optimized in Rust)
  * **Implementation:**
    1.  Attempt forward semantic trace (following data flow).
    2.  Fallback to reverse dependency check if direct flow is broken but a dependency exists.

<!-- end list -->

```python
def trace(self, source_id: str, target_id: str) -> List[List[str]]:
    src_idx = self._id_to_idx[source_id]
    tgt_idx = self._id_to_idx[target_id]
    # Optimized Rust call
    return rx.all_simple_paths(self._graph, src_idx, tgt_idx)
```

### 3\. Stitching (Fuzzy Matching)

Connects nodes across different domains (e.g., Terraform -\> Python) using token overlap.

  * **Structure:** `TokenIndex` (Inverted Index)
  * **Complexity:** $O(1)$ lookup per token
  * **Logic:**
      * Tokenize node names (e.g., `PAYMENT_DB_HOST` -\> `payment`, `db`, `host`).
      * Index nodes by tokens.
      * Query index to find candidates sharing significant tokens.

## Performance Improvements

Moving to `rustworkx` provided significant gains over the previous NetworkX implementation:

| Operation | NetworkX (Old) | rustworkx (New) | Improvement |
| :--- | :--- | :--- | :--- |
| **Graph Construction** | Python Loop | Rust Vector Ops | **\~5x faster** |
| **Pathfinding** | Pure Python BFS | Parallel Rust | **\~10-50x faster** |
| **Memory Usage** | Heavy Python Objects | Compact Rust Structs | **\~3x reduction** |
| **Descendants** | Recursive Python | Optimized Native | **\~100x faster** |

## Future Enhancements

### 1\. Weighted Impact Scoring

Enhance `get_impacted_nodes` to decay impact score over distance:
$$\text{Score}(node) = \frac{\text{Confidence}(path)}{1 + \text{Distance}}$$

### 2\. Cycle Detection & breaking

Use `rustworkx.simple_cycles` to detect circular dependencies (e.g., A reads B, B reads A) that might cause infinite analysis loops or deployment deadlocks.

### 3\. Parallel Subgraph Analysis

For massive monorepos, partition the graph into disjoint subgraphs (using `rustworkx.connected_components`) and run semantic analysis on each component in parallel threads.
