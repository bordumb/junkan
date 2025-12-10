# Confidence Levels

Understanding HIGH, MEDIUM, and LOW confidence scores in jnkn.

## Current Design

Every cross-domain edge in jnkn's dependency graph carries a confidence score between 0.0 and 1.0. This score reflects how certain jnkn is that the relationship is real, not a false positive. The confidence system is designed around a core principle: **every match must be explainable**.

### Confidence Tiers

| Level | Score Range | Meaning | Example |
|-------|-------------|---------|---------|
| **HIGH** | 0.80 - 1.00 | Strong evidence of relationship | Exact/normalized name match |
| **MEDIUM** | 0.50 - 0.79 | Likely related, some uncertainty | 3+ significant token overlap |
| **LOW** | 0.00 - 0.49 | Weak evidence, may be false positive | Single token match with penalties |

The default minimum threshold is 0.5, meaning only MEDIUM and HIGH confidence matches create edges.

### Signal-Based Scoring

Confidence is built from **signals**—evidence that two artifacts are related:

```python
class ConfidenceSignal(StrEnum):
    EXACT_MATCH = "exact_match"           # "db_host" == "db_host"
    NORMALIZED_MATCH = "normalized_match" # "DB_HOST" == "db_host" after normalization
    TOKEN_OVERLAP_HIGH = "token_overlap_high"    # 3+ significant tokens shared
    TOKEN_OVERLAP_MEDIUM = "token_overlap_medium" # 2 significant tokens shared
    SUFFIX_MATCH = "suffix_match"         # target ends with source
    PREFIX_MATCH = "prefix_match"         # target starts with source
    CONTAINS = "contains"                 # target contains source (weak)
    SINGLE_TOKEN = "single_token"         # Only 1 token match (weakest)
```

Each signal has a configurable weight:

```python
signal_weights = {
    ConfidenceSignal.EXACT_MATCH: 1.0,
    ConfidenceSignal.NORMALIZED_MATCH: 0.9,
    ConfidenceSignal.TOKEN_OVERLAP_HIGH: 0.8,
    ConfidenceSignal.TOKEN_OVERLAP_MEDIUM: 0.6,
    ConfidenceSignal.SUFFIX_MATCH: 0.7,
    ConfidenceSignal.PREFIX_MATCH: 0.7,
    ConfidenceSignal.CONTAINS: 0.4,
    ConfidenceSignal.SINGLE_TOKEN: 0.2,
}
```

### Penalty System

Penalties **reduce** confidence when matches have concerning characteristics:

```python
class PenaltyType(StrEnum):
    SHORT_TOKEN = "short_token"      # Tokens < 4 chars are less reliable
    COMMON_TOKEN = "common_token"    # Generic tokens like "id", "host", "key"
    AMBIGUITY = "ambiguity"          # Multiple potential matches exist
    LOW_VALUE_TOKEN = "low_value_token"  # Cloud prefixes like "aws", "gcp"
```

Penalty multipliers are applied multiplicatively:

```python
penalty_multipliers = {
    PenaltyType.SHORT_TOKEN: 0.5,     # Cuts score in half
    PenaltyType.COMMON_TOKEN: 0.7,    # 30% reduction
    PenaltyType.AMBIGUITY: 0.8,       # 20% reduction per alternative
    PenaltyType.LOW_VALUE_TOKEN: 0.6, # 40% reduction
}
```

### Common and Low-Value Tokens

Certain tokens are flagged as providing weak signal:

**Common tokens** (very generic, match many things):
```python
common_tokens = {
    "id", "db", "host", "url", "key", "name", "type", "data",
    "info", "temp", "test", "api", "app", "env", "var", "val",
    "config", "setting", "path", "port", "user", "password",
    "secret", "token", "auth", "log", "file", "dir", "src",
    "dst", "in", "out", "err", "msg", "str", "int", "num",
}
```

**Low-value tokens** (provide some signal but reduced):
```python
low_value_tokens = {
    "aws", "gcp", "azure", "main", "default", "primary",
    "production", "prod", "staging", "dev", "development",
    "internal", "external", "public", "private", "local",
    "remote", "master", "slave", "read", "write",
}
```

### Score Calculation

The `ConfidenceCalculator` combines signals and penalties:

```python
class ConfidenceCalculator:
    def calculate(
        self,
        source_name: str,
        target_name: str,
        source_tokens: List[str],
        target_tokens: List[str],
        matched_tokens: Optional[List[str]] = None,
        alternative_match_count: int = 0,
    ) -> ConfidenceResult:
        # 1. Evaluate all signals
        signal_results = self._evaluate_signals(
            source_name, target_name,
            source_tokens, target_tokens,
            matched_tokens
        )
        
        # 2. Evaluate penalties
        penalty_results = self._evaluate_penalties(
            matched_tokens, alternative_match_count
        )
        
        # 3. Calculate base score (max signal, not sum)
        base_score = self._calculate_base_score(signal_results)
        
        # 4. Apply penalties multiplicatively
        final_score = self._apply_penalties(base_score, penalty_results)
        
        return ConfidenceResult(score=final_score, ...)
```

**Important**: The base score uses the **maximum** signal weight, not the sum. This prevents multiple weak signals from inflating scores:

```python
def _calculate_base_score(self, signal_results: List[SignalResult]) -> float:
    matched_weights = [s.weight for s in signal_results if s.matched]
    if not matched_weights:
        return 0.0
    
    # Use max weight, with small bonus for additional signals
    max_weight = max(matched_weights)
    bonus = min(0.1, (len(matched_weights) - 1) * 0.02)
    
    return min(1.0, max_weight + bonus)
```

### Explainability

Every confidence result includes a human-readable explanation:

```python
result = calculator.calculate(
    source_name="PAYMENT_DB_HOST",
    target_name="payment_db_host",
    source_tokens=["payment", "db", "host"],
    target_tokens=["payment", "db", "host"]
)

print(calculator.explain(result))
```

Output:
```
Match: PAYMENT_DB_HOST → payment_db_host
Confidence: 0.90

Signals:
  ✓ normalized_match (0.90)
    → 'paymentdbhost' == 'paymentdbhost'

Penalties: None

Score Breakdown:
  Base: 0.90
  Final: 0.90
```

### Ambiguity Penalty Example

When multiple targets could match a source, confidence is reduced:

```python
# Source: DB_HOST
# Potential targets: payment_db_host, orders_db_host, users_db_host

# Each match gets penalized for ambiguity
# penalty = 0.8 ** (1 + (alternative_count - 2) * 0.2)

# With 3 alternatives:
# penalty = 0.8 ** (1 + 0.2) = 0.8 ** 1.2 ≈ 0.76
```

## Real-World Examples

### HIGH Confidence (0.90)

```
Source: env:STRIPE_API_KEY
Target: infra:stripe_api_key

Signals:
  ✓ normalized_match (0.90)
    → 'stripeapikey' == 'stripeapikey'
  ✓ token_overlap_high (0.80)
    → 3 significant tokens: ['stripe', 'api', 'key']

Penalties: None

Final Score: 0.90 (HIGH)
```

### MEDIUM Confidence (0.63)

```
Source: env:DB_CONNECTION_URL
Target: infra:database_url

Signals:
  ✓ token_overlap_medium (0.60)
    → 2 significant tokens: ['db', 'url']

Penalties:
  - common_token (×0.70)
    → All matched tokens are common: ['db', 'url']
  - short_token (×0.50)
    → Short tokens (< 4 chars): ['db']

Score Breakdown:
  Base: 0.60
  After penalties: 0.60 × 0.70 × 0.50 = 0.21

Wait, that's LOW. Let's recalculate with better tokens...
```

### LOW Confidence (0.35)

```
Source: env:API_KEY
Target: infra:payment_service_key

Signals:
  ✓ single_token (0.20)
    → Single token match: ['key']

Penalties:
  - common_token (×0.70)
    → All matched tokens are common: ['key']
  - ambiguity (×0.64)
    → Source has 5 potential matches

Score Breakdown:
  Base: 0.20
  After penalties: 0.20 × 0.70 × 0.64 = 0.09

Final Score: 0.09 (LOW - filtered out)
```

## Configuration

Confidence thresholds are configurable in `.jnkn/config.yaml`:

```yaml
confidence:
  min_threshold: 0.5  # Only create edges above this score
  
  # Override signal weights
  signal_weights:
    exact_match: 1.0
    normalized_match: 0.9
    token_overlap_high: 0.8
    token_overlap_medium: 0.6
    
  # Override penalty multipliers
  penalty_multipliers:
    short_token: 0.5
    common_token: 0.7
    ambiguity: 0.8
    
  # Customize common tokens for your project
  common_tokens:
    - id
    - key
    - your_custom_prefix
```

## Future Ideas

### Short-term: Confidence Explanations in Output

Include confidence breakdowns in CLI and JSON output:

```json
{
  "edge": {
    "source": "infra:payment_db_host",
    "target": "env:PAYMENT_DB_HOST",
    "confidence": 0.90,
    "confidence_breakdown": {
      "base_score": 0.90,
      "signals": [
        {"type": "normalized_match", "weight": 0.90}
      ],
      "penalties": []
    }
  }
}
```

### Short-term: Project-Specific Common Tokens

Auto-detect common tokens from the codebase:

```python
def detect_common_tokens(graph: DependencyGraph, threshold: float = 0.2) -> Set[str]:
    """Tokens appearing in >20% of nodes are likely common."""
    token_counts = Counter()
    total_nodes = graph.node_count
    
    for node in graph.iter_nodes():
        for token in node.tokens:
            token_counts[token] += 1
    
    return {t for t, c in token_counts.items() if c / total_nodes > threshold}
```

### Medium-term: Confidence Calibration

Track false positive rates to adjust weights:

```python
class ConfidenceCalibrator:
    def record_feedback(self, edge: Edge, is_correct: bool):
        """Record user feedback on match quality."""
        self.feedback_log.append({
            "edge": edge,
            "predicted_confidence": edge.confidence,
            "actual_correct": is_correct
        })
    
    def calibrate(self) -> Dict[str, float]:
        """Adjust weights based on actual accuracy."""
        # If normalized_match has 95% accuracy but weight is 0.9,
        # maybe increase to 0.95
        pass
```

### Medium-term: Multi-Factor Scoring

Add additional signals beyond name matching:

- **Co-location**: Files in same directory get bonus
- **Co-change**: Files that change together in commits
- **Documentation**: README or comments mentioning relationship
- **Import patterns**: Transitive dependency chains

### Long-term: ML-Based Confidence

Train a classifier on confirmed matches:

```python
class MLConfidenceScorer:
    def __init__(self, model_path: str):
        self.model = load_model(model_path)
    
    def predict(self, source: Node, target: Node) -> float:
        features = self._extract_features(source, target)
        # Features: token overlap, edit distance, file proximity,
        # node types, language pair, etc.
        return self.model.predict_proba(features)[0][1]
```

### Long-term: Confidence Decay

Reduce confidence for stale matches:

```python
def calculate_with_decay(self, edge: Edge, last_confirmed: datetime) -> float:
    """Reduce confidence for old, unconfirmed matches."""
    days_since_confirmation = (datetime.now() - last_confirmed).days
    decay_factor = 0.99 ** (days_since_confirmation / 30)  # 1% decay per month
    return edge.confidence * decay_factor
```