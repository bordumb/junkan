# Token Matching

Fuzzy matching logic for discovering cross-domain dependencies.

## Current Design

jnkn's core innovation is connecting artifacts across technology domains (Python code, Terraform infrastructure, Kubernetes configs, dbt models) through heuristic token matching. When exact references don't exist in code, we infer relationships by matching naming patterns.

### The Problem

Consider this real-world scenario:

```python
# Python application code
db_host = os.getenv("PAYMENT_DB_HOST")
```

```hcl
# Terraform infrastructure
output "payment_db_host" {
  value = aws_db_instance.payment.address
}
```

There's no import statement, no explicit reference—just a naming convention that humans recognize as related. jnkn's token matching engine detects this relationship automatically.

### Normalization

Before matching, names are normalized to remove formatting differences:

```python
@staticmethod
def normalize(name: str) -> str:
    """
    Normalize a name by lowercasing and removing separators.
    
    Examples:
        "Payment_DB_Host" -> "paymentdbhost"
        "payment-db-host" -> "paymentdbhost"
        "PAYMENT.DB.HOST" -> "paymentdbhost"
    """
    result = name.lower()
    for sep in ["_", ".", "-", "/", ":"]:
        result = result.replace(sep, "")
    return result
```

This allows matching across different casing conventions:
- `PAYMENT_DB_HOST` (SCREAMING_SNAKE_CASE in env vars)
- `payment_db_host` (snake_case in Terraform)
- `PaymentDbHost` (PascalCase in some configs)

### Tokenization

Names are split into constituent tokens for partial matching:

```python
@staticmethod
def tokenize(name: str) -> List[str]:
    """
    Split a name into constituent tokens.
    
    Examples:
        "Payment_DB_Host" -> ['payment', 'db', 'host']
        "PAYMENT_DATABASE_CONNECTION_URL" -> ['payment', 'database', 'connection', 'url']
    """
    normalized = name.lower()
    for sep in ["_", ".", "-", "/", ":"]:
        normalized = normalized.replace(sep, " ")
    return [t.strip() for t in normalized.split() if t.strip()]
```

Tokens are stored on nodes during parsing and indexed for O(1) lookups during stitching.

### Match Strategies

The `MatchConfig` defines multiple matching strategies with different confidence weights:

```python
class MatchConfig:
    def __init__(self):
        self.min_confidence = 0.5          # Minimum score to create edge
        self.min_token_overlap = 2         # Minimum shared tokens
        self.min_token_length = 2          # Ignore single-char tokens
        
        self.strategy_weights = {
            MatchStrategy.EXACT: 1.0,       # "db_host" == "db_host"
            MatchStrategy.NORMALIZED: 0.95, # "DB_HOST" matches "db_host"
            MatchStrategy.TOKEN_OVERLAP: 0.85,  # Share 2+ significant tokens
            MatchStrategy.SUFFIX: 0.75,     # "primary_db_host" ends with "db_host"
            MatchStrategy.PREFIX: 0.75,     # "db_host_primary" starts with "db_host"
            MatchStrategy.CONTAINS: 0.6,    # "my_db_host_v2" contains "db_host"
        }
```

### Jaccard Similarity

Token overlap uses Jaccard similarity coefficient:

```python
@staticmethod
def significant_token_overlap(
    tokens1: List[str],
    tokens2: List[str],
    min_length: int = 2
) -> Tuple[List[str], float]:
    """
    Calculate overlap between token lists.
    
    Returns (overlapping_tokens, jaccard_score)
    """
    # Filter insignificant tokens
    sig1 = [t for t in tokens1 if len(t) >= min_length]
    sig2 = [t for t in tokens2 if len(t) >= min_length]
    
    set1 = set(sig1)
    set2 = set(sig2)
    overlap = set1 & set2
    union = set1 | set2
    
    if not union:
        return [], 0.0
    
    jaccard = len(overlap) / len(union)
    return list(overlap), jaccard
```

### Stitching Rules

The `EnvVarToInfraRule` is the primary stitching rule, connecting environment variables to infrastructure resources:

```python
class EnvVarToInfraRule(StitchingRule):
    """Links environment variables to infrastructure resources."""
    
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        edges = []
        
        # Get all env var nodes and infra nodes
        env_nodes = graph.get_nodes_by_type(NodeType.ENV_VAR)
        infra_nodes = graph.get_nodes_by_type(NodeType.INFRA_RESOURCE)
        infra_nodes.extend(graph.get_nodes_by_type(NodeType.CONFIG_KEY))
        
        # Build lookup structures
        infra_by_normalized: Dict[str, List[Node]] = defaultdict(list)
        infra_by_tokens: Dict[str, List[Node]] = defaultdict(list)
        
        for infra in infra_nodes:
            normalized = TokenMatcher.normalize(infra.name)
            infra_by_normalized[normalized].append(infra)
            
            for token in infra.tokens:
                if len(token) >= self.config.min_token_length:
                    infra_by_tokens[token].append(infra)
        
        # Match each env var
        for env in env_nodes:
            best_matches = {}
            
            # Strategy 1: Normalized match (high confidence)
            for infra in infra_by_normalized.get(TokenMatcher.normalize(env.name), []):
                match = MatchResult(
                    source_node=infra.id,
                    target_node=env.id,
                    strategy=MatchStrategy.NORMALIZED,
                    confidence=0.95,
                    matched_tokens=env.tokens
                )
                self._update_best_match(best_matches, infra.id, match)
            
            # Strategy 2: Token overlap (medium confidence)
            for infra_id in self._find_token_candidates(env.tokens, infra_by_tokens):
                infra = graph.get_node(infra_id)
                overlap, score = TokenMatcher.significant_token_overlap(
                    env.tokens, infra.tokens, self.config.min_token_length
                )
                
                if len(overlap) >= self.config.min_token_overlap:
                    match = MatchResult(
                        source_node=infra_id,
                        target_node=env.id,
                        strategy=MatchStrategy.TOKEN_OVERLAP,
                        confidence=min(0.85, score + len(overlap) * 0.1),
                        matched_tokens=overlap
                    )
                    self._update_best_match(best_matches, infra_id, match)
            
            # Create edges for matches above threshold
            for infra_id, match in best_matches.items():
                if match.confidence >= self.config.min_confidence:
                    edges.append(Edge(
                        source_id=infra_id,
                        target_id=env.id,
                        type=RelationshipType.PROVIDES,
                        confidence=match.confidence,
                        metadata={
                            "rule": "EnvVarToInfraRule",
                            "matched_tokens": match.matched_tokens,
                            "explanation": match.explanation
                        }
                    ))
        
        return edges
```

### Best Match Selection

When multiple infrastructure resources could match an environment variable, the highest-confidence match wins:

```python
def _update_best_match(
    self,
    best_matches: Dict[str, MatchResult],
    target_id: str,
    match: MatchResult
):
    """Keep only the highest-confidence match per target."""
    existing = best_matches.get(target_id)
    if existing is None or match.confidence > existing.confidence:
        best_matches[target_id] = match
```

### InfraToInfraRule

A secondary rule discovers relationships between infrastructure resources based on naming patterns:

```python
class InfraToInfraRule(StitchingRule):
    """Links infrastructure resources to each other."""
    
    def apply(self, graph: DependencyGraph) -> List[Edge]:
        # Determines direction based on resource type hierarchy:
        # output > variable > data > resource > module
        pass
```

## Configuration

Token matching behavior is configurable via `.jnkn/config.yaml`:

```yaml
stitching:
  min_confidence: 0.5      # Threshold for creating edges
  min_token_overlap: 2     # Minimum shared tokens
  min_token_length: 2      # Ignore tiny tokens
  
  # Override default weights
  strategy_weights:
    exact: 1.0
    normalized: 0.95
    token_overlap: 0.85
    suffix: 0.75
    prefix: 0.75
    contains: 0.6
```

## Future Ideas

### Short-term: Configurable Stop Words

Add project-specific common tokens to ignore:

```yaml
stitching:
  ignore_tokens:
    - "aws"
    - "prod"
    - "staging"
    - "primary"
    - "main"
```

### Short-term: Semantic Similarity

Use edit distance (Levenshtein) for typo tolerance:

```python
def fuzzy_match(name1: str, name2: str, threshold: float = 0.8) -> bool:
    """Match names that are similar but not identical."""
    from difflib import SequenceMatcher
    ratio = SequenceMatcher(None, name1.lower(), name2.lower()).ratio()
    return ratio >= threshold
```

### Medium-term: Context-Aware Matching

Consider file proximity and project structure:

```python
def context_bonus(source_path: str, target_path: str) -> float:
    """Boost confidence for co-located files."""
    source_dir = Path(source_path).parent
    target_dir = Path(target_path).parent
    
    if source_dir == target_dir:
        return 0.1  # Same directory
    elif source_dir.parent == target_dir.parent:
        return 0.05  # Sibling directories
    return 0.0
```

### Medium-term: Pattern Learning

Learn project-specific naming conventions from confirmed matches:

```python
class PatternLearner:
    def learn_from_confirmed(self, source_name: str, target_name: str):
        """Extract transformation pattern from user-confirmed match."""
        # e.g., "PAYMENT_DB_HOST" -> "payment_db_host"
        # Learn: SCREAMING_SNAKE -> snake_case is a valid pattern
        pass
    
    def suggest_matches(self, name: str) -> List[str]:
        """Apply learned patterns to suggest potential matches."""
        pass
```

### Long-term: Embedding-Based Matching

Use code embeddings for semantic similarity beyond lexical matching:

```python
class EmbeddingMatcher:
    def __init__(self, model: str = "code-search-ada"):
        self.encoder = load_embedding_model(model)
        self.index = None
    
    def build_index(self, nodes: List[Node]):
        """Build vector index from node names and context."""
        embeddings = []
        for node in nodes:
            context = f"{node.name} {node.path} {' '.join(node.tokens)}"
            embeddings.append(self.encoder.encode(context))
        self.index = build_faiss_index(embeddings)
    
    def find_similar(self, query: str, k: int = 5) -> List[Tuple[str, float]]:
        """Find semantically similar nodes."""
        query_vec = self.encoder.encode(query)
        distances, indices = self.index.search(query_vec, k)
        return [(self.nodes[i].id, 1 - d) for i, d in zip(indices, distances)]
```

### Long-term: Multi-Language Convention Mapping

Map naming conventions across language ecosystems:

| Source | Target | Pattern |
|--------|--------|---------|
| Python (`DB_HOST`) | Terraform (`db_host`) | SCREAMING_SNAKE → snake_case |
| Kubernetes (`db-host`) | Python (`DB_HOST`) | kebab-case → SCREAMING_SNAKE |
| JavaScript (`dbHost`) | Terraform (`db_host`) | camelCase → snake_case |

```python
class ConventionMapper:
    def __init__(self):
        self.transformations = {
            ("python", "terraform"): self._screaming_to_snake,
            ("kubernetes", "python"): self._kebab_to_screaming,
            ("javascript", "terraform"): self._camel_to_snake,
        }
    
    def transform(self, name: str, from_lang: str, to_lang: str) -> str:
        """Apply convention transformation."""
        key = (from_lang, to_lang)
        if key in self.transformations:
            return self.transformations[key](name)
        return name
```