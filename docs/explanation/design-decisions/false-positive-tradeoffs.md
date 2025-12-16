# Precision vs Recall

Philosophy on false positives and the trade-offs in dependency detection.

## Current Design

jnkn deliberately prioritizes **precision over recall** in its default configuration. This means we would rather miss some real dependencies (false negatives) than flood users with spurious connections (false positives). The reasoning is grounded in how developers actually use static analysis tools.

### The False Positive Problem

Industry research consistently shows that **false positive rate is the single most important factor for developer adoption** of static analysis tools. Google's Tricorder system found that developers ignore tools that "cry wolf"—once trust is lost, the tool becomes noise rather than signal.

DeepSource targets a **<5% false positive rate** through aggressive post-processing and filtering. ESLint's success comes partly from its granular suppression system. SonarQube struggled with adoption until they added "Quality Gates" that let teams define acceptable noise levels.

jnkn's heuristic token matching is inherently probabilistic. A match between `DB_HOST` and `db_host` might be correct, but it might also be coincidental if both are unrelated database configurations in different services.

### The Threshold Decision

The default minimum confidence threshold of **0.5** represents our precision/recall trade-off:

```python
class MatchConfig:
    min_confidence: float = 0.3  # Default threshold
```

At this threshold:
- **Exact matches** (confidence 1.0): Always included
- **Normalized matches** (confidence 0.9): Always included  
- **High token overlap** (confidence 0.8): Always included
- **Medium token overlap** (confidence 0.6): Usually included
- **Single token matches** (confidence 0.2): Filtered out
- **Penalized matches**: May fall below threshold

### Adjustable Thresholds

Users can tune the precision/recall trade-off in configuration:

```yaml
# .jnkn/config.yaml

# High precision (fewer false positives, may miss some real deps)
stitching:
  min_confidence: 0.7

# Balanced (default)
stitching:
  min_confidence: 0.5

# High recall (more dependencies found, more false positives)
stitching:
  min_confidence: 0.3
```

### Penalty System as Precision Tool

The penalty system specifically targets common false positive patterns:

**Short tokens** (`db`, `id`, `key`) match too broadly:
```python
if len(token) < 4:
    confidence *= 0.5  # 50% penalty
```

**Common tokens** are generic and unreliable:
```python
common_tokens = {"id", "db", "host", "url", "key", "name", "type", "data", ...}

if all(t in common_tokens for t in matched_tokens):
    confidence *= 0.7  # 30% penalty
```

**Ambiguous matches** where multiple targets exist:
```python
if alternative_match_count > 2:
    confidence *= 0.8 ** (1 + (alternative_match_count - 2) * 0.2)
```

### Suppression System

When false positives do occur, the suppression system allows permanent exclusion:

```yaml
# .jnkn/suppressions.yaml
suppressions:
  - source_pattern: "env:*_ID"
    target_pattern: "infra:*"
    reason: "Generic ID variables don't map to infrastructure"
    
  - source_pattern: "env:LOG_LEVEL"
    target_pattern: "infra:*"
    reason: "Application config, not infrastructure"
```

The CLI provides commands for managing suppressions:

```bash
# Add a suppression
jnkn suppress add --source "env:API_KEY" --target "infra:legacy_*" --reason "Unrelated"

# List active suppressions
jnkn suppress list

# Remove a suppression
jnkn suppress remove --id "supp_abc123"
```

### Explainability for Triage

When users see unexpected matches, the `explain` command helps triage:

```bash
jnkn explain "env:PAYMENT_DB_HOST" "infra:payment_db_host"
```

Output:
```
Match: PAYMENT_DB_HOST → payment_db_host
Confidence: 0.90

Signals:
  ✓ normalized_match (0.90)
    → 'paymentdbhost' == 'paymentdbhost'

Penalties: None

This is likely a TRUE POSITIVE - high confidence, no penalties.
```

```bash
jnkn explain "env:DB_URL" "infra:cache_url"
```

Output:
```
Match: DB_URL → cache_url
Confidence: 0.35

Signals:
  ✓ single_token (0.20)
    → Single token match: ['url']

Penalties:
  - common_token (×0.70)
    → All matched tokens are common: ['url']
  - ambiguity (×0.64)
    → Source has 4 potential matches

This is likely a FALSE POSITIVE - low confidence, multiple penalties.
Consider suppressing this match.
```

### The "Why Not" Explanation

For debugging missing connections, `explain-why-not` shows why a match wasn't made:

```bash
jnkn explain-why-not "env:CUSTOM_VAR" "infra:my_custom_variable"
```

Output:
```
WHY NO MATCH?

✗ Score (0.42) is below threshold (0.50)

Details:
  Source: env:CUSTOM_VAR
  Target: infra:my_custom_variable
  Source tokens: ['custom', 'var']
  Target tokens: ['my', 'custom', 'variable']
  Common tokens: ['custom']

  ! Only 1 significant token overlap
  
  To reach threshold, need +0.08 confidence

Options:
  1. Lower min_confidence to 0.4
  2. Add explicit edge in config
  3. Rename to improve token alignment
```

## Trade-off Philosophy

### When to Prioritize Precision

- **CI/CD gates**: False positives block deployments, creating friction
- **Large codebases**: High node counts amplify false positive noise
- **Compliance reporting**: False positives create audit overhead
- **Developer trust**: Initial adoption requires low noise

### When to Prioritize Recall

- **Security audits**: Missing a real dependency could be costly
- **Migration planning**: Need comprehensive impact understanding
- **Exploration**: Understanding unfamiliar codebases
- **Small projects**: Lower base rate makes false positives manageable

### Recommended Configurations

**Conservative (CI/CD)**:
```yaml
stitching:
  min_confidence: 0.7
  min_token_overlap: 3
```

**Balanced (General use)**:
```yaml
stitching:
  min_confidence: 0.5
  min_token_overlap: 2
```

**Exploratory (Audits)**:
```yaml
stitching:
  min_confidence: 0.3
  min_token_overlap: 1
```

## Future Ideas

### Short-term: Confidence Bands in Output

Show confidence tiers in CLI output:

```
Blast Radius for infra:payment_db_host:

HIGH CONFIDENCE (0.8+):
  → env:PAYMENT_DB_HOST (0.90)
  → file://services/payment/config.py (0.85)

MEDIUM CONFIDENCE (0.5-0.8):
  → env:DB_HOST (0.62)
  → file://services/shared/database.py (0.55)

LOW CONFIDENCE (hidden by default):
  → env:HOST (0.35) [use --show-low to display]
```

### Short-term: Per-Rule Thresholds

Different rules might warrant different thresholds:

```yaml
stitching:
  rules:
    EnvVarToInfraRule:
      min_confidence: 0.6  # Higher bar for env-to-infra
    InfraToInfraRule:
      min_confidence: 0.4  # Lower bar for infra-to-infra
```

### Medium-term: Feedback Loop

Track accuracy over time based on user actions:

```python
class FeedbackTracker:
    def record_suppression(self, edge: Edge):
        """User suppressed = likely false positive."""
        self._false_positives.append(edge)
    
    def record_confirmation(self, edge: Edge):
        """User confirmed = true positive."""
        self._true_positives.append(edge)
    
    def calculate_precision(self) -> float:
        tp = len(self._true_positives)
        fp = len(self._false_positives)
        return tp / (tp + fp) if (tp + fp) > 0 else 1.0
```

### Medium-term: Anomaly Detection

Flag matches that deviate from project patterns:

```python
def detect_anomalous_match(edge: Edge, graph: DependencyGraph) -> bool:
    """Flag if match is unusual compared to similar matches."""
    # If most env vars from services/payment/ link to infra:payment_*
    # but this one links to infra:orders_*, it's anomalous
    similar_sources = get_similar_sources(edge.source_id, graph)
    typical_targets = get_typical_targets(similar_sources, graph)
    return edge.target_id not in typical_targets
```

### Long-term: ML-Calibrated Thresholds

Train on labeled data to optimize threshold:

```python
def optimize_threshold(
    labeled_edges: List[Tuple[Edge, bool]],  # (edge, is_correct)
    target_precision: float = 0.95
) -> float:
    """Find threshold that achieves target precision."""
    # Sort edges by confidence
    sorted_edges = sorted(labeled_edges, key=lambda x: x[0].confidence, reverse=True)
    
    # Find threshold where precision drops below target
    tp, fp = 0, 0
    for edge, is_correct in sorted_edges:
        if is_correct:
            tp += 1
        else:
            fp += 1
        precision = tp / (tp + fp)
        if precision < target_precision:
            return edge.confidence
    
    return 0.0  # Include all if target met
```

### Long-term: Context-Aware Precision

Adjust precision dynamically based on context:

```python
def context_adjusted_threshold(
    base_threshold: float,
    file_path: Path,
    graph: DependencyGraph
) -> float:
    """Adjust threshold based on file/project context."""
    # Critical paths need higher precision
    if "payment" in str(file_path) or "auth" in str(file_path):
        return base_threshold + 0.1
    
    # Test files can tolerate lower precision
    if "test" in str(file_path):
        return base_threshold - 0.1
    
    # High-connectivity nodes need higher precision
    node_degree = len(graph.get_direct_dependents(f"file://{file_path}"))
    if node_degree > 10:
        return base_threshold + 0.05
    
    return base_threshold
```