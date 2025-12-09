# Configure Confidence

Tune confidence thresholds to balance precision and recall.

## Understanding Confidence

Confidence scores range from 0.0 to 1.0:

| Score | Level | Meaning |
|-------|-------|---------|
| 0.8 - 1.0 | HIGH | Very likely a real dependency |
| 0.5 - 0.8 | MEDIUM | Probably related, review recommended |
| 0.0 - 0.5 | LOW | Weak signal, often false positive |

## Setting the Threshold

In `.jnkn/config.yaml`:

```yaml
stitching:
  min_confidence: 0.5  # Default
```

Higher threshold = fewer matches, fewer false positives:

```yaml
stitching:
  min_confidence: 0.7  # More conservative
```

Lower threshold = more matches, may catch subtle dependencies:

```yaml
stitching:
  min_confidence: 0.3  # More permissive
```

## Per-Rule Thresholds

Different rules can have different thresholds:

```yaml
stitching:
  min_confidence: 0.5  # Default
  
  rule_overrides:
    EnvVarToInfraRule:
      min_confidence: 0.6  # Stricter for env→infra
    K8sToSecretRule:
      min_confidence: 0.4  # More permissive for K8s
```

## Signal Weights

Customize how confidence is calculated:

```yaml
stitching:
  confidence:
    signals:
      exact_match: 1.0
      normalized_match: 0.9
      token_overlap_high: 0.85
      token_overlap_medium: 0.7
      suffix_match: 0.6
      contains: 0.5
    
    penalties:
      short_token: 0.5      # Tokens < 4 chars
      common_token: 0.7     # Generic words like "url", "host"
      ambiguous: 0.8        # Multiple possible matches
```

## Token Configuration

### Blocked Tokens

Tokens that provide no matching signal:

```yaml
stitching:
  blocked_tokens:
    - id
    - key
    - url
    - host
    - port
    - name
    - value
    - config
```

### Minimum Token Length

Ignore short tokens:

```yaml
stitching:
  min_token_length: 3  # Default
```

### Low-Value Tokens

Tokens that reduce confidence when matched:

```yaml
stitching:
  low_value_tokens:
    - aws
    - prod
    - dev
    - main
    - test
```

## Finding the Right Balance

### Start Conservative

```yaml
stitching:
  min_confidence: 0.7
```

Run `jnkn scan` and check results. If you're missing real dependencies, lower the threshold.

### Check What You're Missing

```bash
jnkn explain env:DATABASE_URL infra:db_instance --why-not
```

If the confidence is 0.65 but the match is real, consider lowering your threshold.

### Iterate

1. Scan with current settings
2. Review a sample of matches
3. Adjust threshold or add suppressions
4. Repeat

## Environment Variable Override

Override in CI without changing config:

```bash
JUNKAN_MIN_CONFIDENCE=0.6 jnkn scan
```
