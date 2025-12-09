# Too Many False Positives

Reduce incorrect matches when Jnkn links unrelated artifacts.

## Quick Fixes

### 1. Raise Confidence Threshold

```yaml
# .jnkn/config.yaml
stitching:
  min_confidence: 0.7  # Up from 0.5
```

### 2. Suppress Known Bad Patterns

```bash
# Generic patterns that match too much
jnkn suppress add "env:*_ID" "infra:*" --reason "ID fields too generic"
jnkn suppress add "env:*_KEY" "infra:*" --reason "KEY fields too generic"
jnkn suppress add "env:HOST" "*" --reason "HOST alone is too generic"
```

### 3. Block Common Tokens

```yaml
# .jnkn/config.yaml
stitching:
  blocked_tokens:
    - id
    - key
    - url
    - host
    - port
    - name
    - config
    - value
    - data
    - type
```

## Systematic Approach

### Step 1: Identify the Problem

List all current matches:

```bash
jnkn stats --edges --type cross_domain
```

### Step 2: Sample and Review

Pick 10 random matches and verify:

```bash
jnkn stats --edges --type cross_domain --format json | jq '.[0:10]'
```

For each, ask: "Is this a real dependency?"

### Step 3: Categorize False Positives

Common categories:

| Category | Example | Solution |
|----------|---------|----------|
| Generic tokens | `HOST` matches everything | Block token |
| Naming collision | `user_id` matches `uuid` | Suppress pattern |
| Low confidence | 0.51 sneaking through | Raise threshold |
| Wrong domain | Test → Prod matches | Suppress pattern |

### Step 4: Apply Fixes

**For generic tokens:**

```yaml
stitching:
  blocked_tokens:
    - host
    - user
```

**For naming collisions:**

```bash
jnkn suppress add "env:USER_ID" "infra:uuid_*" --reason "Collision"
```

**For low confidence:**

```yaml
stitching:
  min_confidence: 0.6
```

**For wrong domain:**

```bash
jnkn suppress add "*" "infra:test_*" --reason "Test infra"
jnkn suppress add "*" "infra:*_dev" --reason "Dev infra"
```

### Step 5: Verify

Rescan and check:

```bash
jnkn scan --full
jnkn stats --edges --type cross_domain
```

## Advanced: Custom Penalties

Add penalties for tokens that reduce confidence:

```yaml
stitching:
  confidence:
    penalties:
      short_token: 0.5    # < 4 chars
      common_token: 0.6   # Generic words
    
  low_value_tokens:
    - aws
    - gcp
    - prod
    - dev
    - staging
    - main
    - default
```

## Advanced: Rule-Specific Tuning

Different rules can have different thresholds:

```yaml
stitching:
  rule_overrides:
    EnvVarToInfraRule:
      min_confidence: 0.7     # Stricter
      blocked_tokens:
        - host
        - port
    
    K8sToSecretRule:
      min_confidence: 0.5     # Default
```

## Measuring Improvement

Track precision over time:

```bash
# Before changes
jnkn stats --edges --type cross_domain | wc -l
# 150 matches

# After changes  
jnkn stats --edges --type cross_domain | wc -l
# 45 matches (70% reduction)
```

Review the remaining matches to ensure you didn't lose real dependencies.

## When to Accept Some False Positives

Consider keeping false positives if:

- Manual review is fast (< 5 matches per PR)
- The cost of missing a real dependency is high
- Your team prefers over-alerting to under-alerting

The goal is **useful signal**, not zero noise.
