# Manage Suppressions

Handle false positives by suppressing incorrect matches.

## Add a Suppression

### Specific Match

```bash
jnkn suppress add "env:HOST" "infra:ghost_writer" \
  --reason "Unrelated - ghost_writer is a logging service"
```

### Pattern Match

Use globs for broader suppression:

```bash
# All *_ID env vars
jnkn suppress add "env:*_ID" "infra:*" \
  --reason "ID fields are too generic"

# All test infrastructure
jnkn suppress add "*" "infra:test_*" \
  --reason "Test infrastructure"

# Specific prefix
jnkn suppress add "env:LEGACY_*" "*" \
  --reason "Legacy vars being deprecated"
```

## List Suppressions

```bash
jnkn suppress list
```

```
ID  Source        Target         Reason                  Enabled  Expires
1   env:HOST      infra:ghost_*  Unrelated services      yes      never
2   env:*_ID      infra:*        ID fields too generic   yes      never
3   *             infra:test_*   Test infrastructure     yes      2024-06-01
```

## Remove a Suppression

By ID:

```bash
jnkn suppress remove 1
```

By pattern:

```bash
jnkn suppress remove --source "env:*_ID" --target "infra:*"
```

## Test a Suppression

Check if a match would be suppressed:

```bash
jnkn suppress test env:USER_ID infra:user_service
```

```
✓ Would be SUPPRESSED by rule 2: "env:*_ID" → "infra:*"
  Reason: ID fields too generic
```

## Temporary Suppressions

Add an expiration date:

```bash
jnkn suppress add "env:X" "infra:Y" \
  --reason "Temporary during migration" \
  --expires 2024-06-01
```

## Enable/Disable

Disable without removing:

```bash
jnkn suppress disable 2
```

Re-enable:

```bash
jnkn suppress enable 2
```

## Suppressions File

Stored in `.jnkn/suppressions.yaml`:

```yaml
suppressions:
  - id: 1
    source_pattern: "env:HOST"
    target_pattern: "infra:ghost_*"
    reason: "Unrelated services"
    enabled: true
    expires: null
    created_at: "2024-01-15T10:30:00Z"
    
  - id: 2
    source_pattern: "env:*_ID"
    target_pattern: "infra:*"
    reason: "ID fields too generic"
    enabled: true
    expires: null
    created_at: "2024-01-15T10:35:00Z"
```

!!! tip "Version Control"
    Commit `.jnkn/suppressions.yaml` to git so the team shares suppressions.

## Glob Patterns

| Pattern | Matches | Doesn't Match |
|---------|---------|---------------|
| `env:*` | `env:X`, `env:DATABASE_URL` | `infra:X` |
| `env:DB_*` | `env:DB_HOST`, `env:DB_PORT` | `env:DATABASE` |
| `*_URL` | `env:DATABASE_URL`, `infra:api_url` | `env:URL_PREFIX` |
| `infra:aws_*` | `infra:aws_rds`, `infra:aws_s3` | `infra:gcp_sql` |

## Bulk Import

Import from JSON:

```bash
cat suppressions.json | jnkn suppress import
```

```json
[
  {"source": "env:*_ID", "target": "infra:*", "reason": "Generic"},
  {"source": "env:HOST", "target": "infra:ghost_*", "reason": "Unrelated"}
]
```

## Export

```bash
jnkn suppress export --format json > suppressions-backup.json
```
