# Why Token Matching

Rationale for our cross-domain linking strategy.

## The Problem

How do you know `env:DATABASE_URL` in Python relates to `output.database_url` in Terraform?

There's no explicit link — it's a **convention**.

## The Alternatives

| Approach | Accuracy | Effort | Coverage |
|----------|----------|--------|----------|
| **Manual annotation** | Perfect | High | Limited |
| **Semantic analysis** | High | Very high | Limited |
| **Token matching** | Good | Low | Broad |

## Why Not Manual Annotation?

```yaml
# Manual mapping file
links:
  - source: env:DATABASE_URL
    target: infra:output.database_url
  - source: env:REDIS_HOST
    target: infra:output.redis_endpoint
```

Problems:

1. **Doesn't scale** — Hundreds of env vars × resources
2. **Gets stale** — New vars aren't added
3. **Human error** — Typos, missed entries
4. **Defeats the purpose** — If you tracked it manually, you wouldn't need Jnkn

## Why Not Semantic Analysis?

Semantic analysis would understand that:
- `aws_rds_instance` provides a database
- `DATABASE_URL` is a database connection string
- Therefore, they're related

Problems:

1. **Requires domain knowledge** — What does `aws_elasticache` provide?
2. **Computationally expensive** — Need embeddings, inference
3. **Brittle** — Custom resources, unusual naming
4. **Overkill** — Names usually tell you what you need

## Why Token Matching Works

In practice, teams use **consistent naming**:

```
Python:          DATABASE_URL
Terraform:       output.database_url
Kubernetes:      secret.database-url
Config file:     database_url

Tokens: [database, url] — identical!
```

Token matching exploits this convention.

## How It Works

### Step 1: Tokenize

Split names on separators and case boundaries:

```
DATABASE_URL     → [database, url]
databaseUrl      → [database, url]  
database-url     → [database, url]
PAYMENT_DB_HOST  → [payment, db, host]
```

### Step 2: Normalize

Lowercase, remove noise:

```
DATABASE_URL → [database, url]
DataBase_URL → [database, url]
```

### Step 3: Compare

Calculate overlap:

```
Source: [database, url]
Target: [database, url]
Overlap: 100% → High confidence
```

### Step 4: Score

Apply penalties for weak matches:

```
Source: [db, host]
Target: [db, host]
Overlap: 100%
Penalty: short tokens (db=2 chars)
Final: Medium confidence
```

## When It Works Well

✅ **Consistent naming** — Teams follow conventions  
✅ **Descriptive names** — `PAYMENT_DATABASE_HOST` not `PDH`  
✅ **Similar patterns** — `*_URL`, `*_HOST`, `*_KEY`  

## When It Struggles

❌ **Abbreviations** — `DB` doesn't match `database`  
❌ **Generic names** — `HOST` matches everything  
❌ **Different conventions** — `camelCase` vs `SCREAMING_SNAKE`  

We mitigate with:
- Blocked tokens (`id`, `key`, etc.)
- Confidence thresholds
- Suppressions for known false positives

## The Tradeoff

Token matching is **heuristic**, not perfect.

```
Precision: ~85-95% (with tuning)
Recall: ~70-85%
```

This is acceptable because:

1. **False positives are visible** — Developers review and suppress
2. **False negatives surface elsewhere** — Tests, prod errors
3. **The alternative is nothing** — No other tool catches this

## Improving Accuracy

### Organization-Level

- Enforce naming conventions
- Document env var → resource mappings
- Run Jnkn in CI to catch drift

### Jnkn-Level

- Tune confidence thresholds
- Add suppressions for known issues
- Custom rules for domain-specific patterns
