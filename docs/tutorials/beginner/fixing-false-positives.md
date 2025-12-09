# Fixing False Positives

Learn to tune Jnkn when it makes incorrect matches.

**Time:** 10 minutes

## When to Suppress

False positives happen when Jnkn links unrelated artifacts due to similar names:

```
env:HOST  ←→  infra:ghost_writer    # Wrong! Just share "host" substring
env:ID    ←→  infra:user_id         # Wrong! "ID" is too generic
```

## Strategy 1: Raise Confidence Threshold

Edit `.jnkn/config.yaml`:

```yaml
stitching:
  min_confidence: 0.6  # Default is 0.5
```

Higher threshold = fewer matches = fewer false positives (but may miss real links).

## Strategy 2: Add Suppressions

Suppress specific patterns that you know are wrong.

### Suppress a Single Match

```bash
jnkn suppress add "env:HOST" "infra:ghost_writer" \
  --reason "Unrelated - ghost_writer is a logging service"
```

### Suppress a Pattern

Use globs to suppress categories:

```bash
# All *_ID env vars are too generic
jnkn suppress add "env:*_ID" "infra:*" \
  --reason "ID fields are too generic for matching"

# Ignore all matches to test infrastructure  
jnkn suppress add "*" "infra:test_*" \
  --reason "Test infrastructure, not production"
```

### List Suppressions

```bash
jnkn suppress list
```

```
ID  Source        Target         Reason                    Expires
1   env:HOST      infra:ghost_*  Unrelated services        never
2   env:*_ID      infra:*        ID fields too generic     never
3   *             infra:test_*   Test infrastructure       2024-03-01
```

### Remove a Suppression

```bash
jnkn suppress remove 1
```

### Test a Suppression

Check if a match would be suppressed:

```bash
jnkn suppress test env:USER_ID infra:user_service
```

```
✓ Would be SUPPRESSED by rule 2: "env:*_ID" → "infra:*"
```

## Strategy 3: Configure Token Filtering

Some tokens are too common to be meaningful. Edit `.jnkn/config.yaml`:

```yaml
stitching:
  blocked_tokens:
    - id
    - key
    - url
    - host
    - port
    - name
  
  min_token_length: 3  # Ignore tokens shorter than this
```

## Suppressions File

Suppressions are stored in `.jnkn/suppressions.yaml`:

```yaml
suppressions:
  - source_pattern: "env:*_ID"
    target_pattern: "infra:*"
    reason: "ID fields are too generic"
    enabled: true
    expires: null
    created_at: "2024-01-15T10:30:00Z"
    
  - source_pattern: "env:HOST"
    target_pattern: "infra:ghost_*"
    reason: "Unrelated services"
    enabled: true
    expires: "2024-06-01"
    created_at: "2024-01-15T10:35:00Z"
```

!!! tip "Commit suppressions to git"
    Suppressions should be version-controlled so the whole team benefits.

## Verifying Your Fixes

After adding suppressions, re-scan:

```bash
jnkn scan --full
```

Check that false positives are gone:

```bash
jnkn blast env:HOST
```

## When to NOT Suppress

Don't suppress just because a match is unexpected. Investigate first:

```bash
jnkn explain env:PAYMENT_DB_HOST infra:payment_database
```

If the confidence is high and the tokens genuinely overlap, the match might be **correct** — you may have discovered a real dependency you didn't know about.

## Next Steps

- [:octicons-arrow-right-24: Configure confidence in detail](../../how-to/configuration/configure-confidence.md)
- [:octicons-arrow-right-24: Understand how matching works](../../explanation/concepts/cross-domain-deps.md)
