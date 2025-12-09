# Confidence Model

How Jnkn scores match quality.

## Overview

Confidence answers: **"How likely is this match correct?"**

```
Final Score = Base Signal × Π(Penalties)
```

A score of 0.85 means "85% confident this is a real dependency."

## Signals

Signals are positive indicators that increase base confidence.

| Signal | Score | Description |
|--------|-------|-------------|
| `exact_match` | 1.0 | Names are identical |
| `normalized_match` | 0.9 | Names equal after normalization |
| `token_overlap_high` | 0.85 | >80% of tokens overlap |
| `token_overlap_medium` | 0.7 | 50-80% overlap |
| `suffix_match` | 0.6 | Names end with same tokens |
| `prefix_match` | 0.6 | Names start with same tokens |
| `contains` | 0.5 | One name contains the other |
| `single_token` | 0.4 | Only one token matches |

**Only the highest signal is used** (they don't stack).

## Penalties

Penalties reduce confidence when matches are weak.

| Penalty | Multiplier | Condition |
|---------|------------|-----------|
| `short_token` | 0.5 | Any matched token < 4 chars |
| `common_token` | 0.7 | Only generic words matched |
| `ambiguous` | 0.8 | Multiple targets could match |
| `low_value` | 0.9 | Matched low-value tokens |

**Penalties stack multiplicatively.**

## Calculation Example

**Match:** `env:DB_HOST` → `infra:db_host`

```
Tokens:
  Source: [db, host]
  Target: [db, host]
  
Signal:
  normalized_match → 0.9 (names equal after normalization)

Penalties:
  short_token (db=2 chars) → ×0.5

Final:
  0.9 × 0.5 = 0.45
```

With threshold 0.5, this match is **rejected** (0.45 < 0.5).

## Another Example

**Match:** `env:PAYMENT_DATABASE_URL` → `infra:payment_db_instance`

```
Tokens:
  Source: [payment, database, url]
  Target: [payment, db, instance]
  
Overlap: [payment] (1 of 3)

Signal:
  single_token → 0.4

Penalties:
  none

Final:
  0.4
```

With threshold 0.5, this is **rejected**.

## High-Confidence Match

**Match:** `env:STRIPE_API_KEY` → `infra:var.stripe_api_key`

```
Tokens:
  Source: [stripe, api, key]
  Target: [stripe, api, key]
  
Signal:
  normalized_match → 0.9

Penalties:
  short_token (api=3, key=3) → ×0.5 × 0.5 = ×0.25? 
  
  No! Penalty applies once per category, not per token.
  short_token → ×0.5

Final:
  0.9 × 0.5 = 0.45
```

Hmm, this is still rejected. Let's tune:

## Tuning Confidence

If good matches are being rejected, you have options:

### Lower the threshold

```yaml
stitching:
  min_confidence: 0.4
```

### Adjust signal weights

```yaml
stitching:
  confidence:
    signals:
      normalized_match: 0.95  # Increase from 0.9
```

### Reduce penalty severity

```yaml
stitching:
  confidence:
    penalties:
      short_token: 0.7  # Less harsh than 0.5
```

### Don't penalize specific tokens

```yaml
stitching:
  min_token_length: 2  # Allow 2-char tokens
```

## Threshold Guidelines

| Threshold | Use Case |
|-----------|----------|
| 0.3 | Discovery mode — find all possible links |
| 0.5 | Balanced (default) |
| 0.7 | Conservative — high precision |
| 0.9 | Very strict — only obvious matches |

## The Tradeoff

```
Lower threshold → More matches → More false positives
Higher threshold → Fewer matches → More false negatives
```

**Jnkn's philosophy:** False positives are worse than false negatives. A developer investigating a bogus alert wastes time. Missing a dependency is caught during testing or review.

## Inspecting Confidence

```bash
jnkn explain env:DB_HOST infra:db_host
```

Shows full breakdown of signals and penalties.
