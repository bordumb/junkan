# suppressions.yaml Reference

Manage false positive suppressions at `.jnkn/suppressions.yaml`.

## Schema

```yaml
suppressions:
  - id: 1
    source_pattern: "env:*_ID"
    target_pattern: "infra:*"
    reason: "ID fields are too generic for matching"
    enabled: true
    expires: null
    created_at: "2024-01-15T10:30:00Z"
    created_by: "user@example.com"
    
  - id: 2
    source_pattern: "env:HOST"
    target_pattern: "infra:ghost_*"
    reason: "ghost_writer is unrelated logging service"
    enabled: true
    expires: "2024-06-01"
    created_at: "2024-01-15T10:35:00Z"
    created_by: null
```

## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | integer | yes | Unique identifier |
| `source_pattern` | string | yes | Glob pattern for source artifact |
| `target_pattern` | string | yes | Glob pattern for target artifact |
| `reason` | string | no | Why this suppression exists |
| `enabled` | boolean | no | Whether suppression is active (default: true) |
| `expires` | string | no | ISO 8601 date when suppression expires |
| `created_at` | string | no | ISO 8601 timestamp of creation |
| `created_by` | string | no | Who created this suppression |

## Glob Patterns

| Pattern | Matches |
|---------|---------|
| `*` | Any characters |
| `?` | Single character |
| `[abc]` | Character class |
| `[!abc]` | Negated character class |

### Examples

| Pattern | Matches | Doesn't Match |
|---------|---------|---------------|
| `env:*` | `env:X`, `env:DATABASE_URL` | `infra:X` |
| `env:DB_*` | `env:DB_HOST`, `env:DB_PORT` | `env:DATABASE` |
| `*_URL` | `env:DATABASE_URL`, `infra:api_url` | `env:URL_PREFIX` |
| `env:???` | `env:ABC`, `env:XYZ` | `env:ABCD` |
| `env:[A-Z]*` | `env:ABC` | `env:abc` |

## Order of Evaluation

Suppressions are evaluated in order. First match wins.

```yaml
suppressions:
  # This matches first
  - source_pattern: "env:DATABASE_URL"
    target_pattern: "infra:main_db"
    reason: "Specific exception"
    enabled: true
    
  # This is more general but evaluated second
  - source_pattern: "env:*"
    target_pattern: "infra:*"
    reason: "Broad suppression"
    enabled: true
```

## Expiration

Suppressions can expire:

```yaml
- source_pattern: "env:TEMP_*"
  target_pattern: "*"
  reason: "Temporary during migration"
  expires: "2024-06-01"  # Ignored after this date
```

Expired suppressions remain in the file but are not applied.

## Disabling

Disable without removing:

```yaml
- source_pattern: "env:X"
  target_pattern: "infra:Y"
  enabled: false  # Kept for reference but not applied
```

## Managing via CLI

```bash
# Add
jnkn suppress add "env:*_ID" "infra:*" --reason "Generic"

# List
jnkn suppress list

# Remove
jnkn suppress remove 1

# Enable/disable
jnkn suppress disable 2
jnkn suppress enable 2

# Test
jnkn suppress test env:USER_ID infra:user_service
```

## Best Practices

1. **Always add a reason** — Future you will thank you
2. **Use specific patterns** — Avoid `*` → `*`
3. **Set expiration for temporary suppressions**
4. **Commit to version control** — Share with team
5. **Review periodically** — Remove stale suppressions
