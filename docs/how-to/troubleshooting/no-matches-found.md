# No Matches Found

Debug why Jnkn isn't detecting dependencies.

## Check What Was Scanned

```bash
jnkn stats
```

If `Nodes: 0`, no files were parsed.

## Verify File Discovery

```bash
jnkn scan --verbose
```

Look for:

```
Scanning /path/to/project
  Found 0 Python files
  Found 0 Terraform files
```

### Common Causes

**Wrong directory:**

```bash
# Make sure you're in the right place
jnkn scan --dir ./src
```

**Files ignored:**

Check `.jnknignore`:

```gitignore
# This ignores everything!
*
```

**Unsupported extension:**

Jnkn only scans `.py`, `.tf`, `.yaml`, `.yml` by default.

## Verify Pattern Detection

For a specific file:

```bash
jnkn scan --verbose --files src/config.py
```

Look for detected patterns:

```
src/config.py:
  Detected: env:DATABASE_URL (os.getenv)
  Detected: env:API_KEY (pydantic_settings)
```

### Common Causes

**Pattern not supported:**

Check [Supported Patterns](../../reference/patterns/index.md). Your pattern may not be implemented yet.

**Syntax variation:**

```python
# Supported
os.getenv("DATABASE_URL")

# NOT supported (variable key)
key = "DATABASE_URL"
os.getenv(key)
```

**Comments or strings:**

```python
# This is NOT detected (it's a comment)
# os.getenv("DATABASE_URL")

# This is NOT detected (it's a string)
example = 'os.getenv("DATABASE_URL")'
```

## Check Stitching

If nodes exist but no cross-domain edges:

```bash
jnkn stats
```

```
Nodes: 50
Edges: 45
Cross-domain edges: 0  # Problem!
```

### Verify Tokens

```bash
jnkn explain env:DATABASE_URL infra:db_instance
```

```
Source tokens: [database, url]
Target tokens: [db, instance]
Token overlap: 0/2  # No match!
```

**Solution:** The names are too different. Consider:

- Renaming to match conventions
- Creating a custom stitching rule
- Lowering confidence threshold

### Check Confidence

```bash
jnkn explain env:DB_HOST infra:db_host
```

```
Confidence: 0.45 (REJECTED)
Threshold: 0.50
```

**Solution:** Lower the threshold:

```yaml
stitching:
  min_confidence: 0.4
```

## Check for Suppressions

A suppression might be hiding the match:

```bash
jnkn suppress test env:DATABASE_URL infra:db_instance
```

```
✓ Would be SUPPRESSED by rule 2
```

**Solution:** Remove or disable the suppression:

```bash
jnkn suppress remove 2
```

## Enable Debug Logging

```bash
JUNKAN_LOG_LEVEL=DEBUG jnkn scan
```

This shows detailed parsing and matching information.

## Still Stuck?

1. Check GitHub Issues for similar problems
2. Run `jnkn feedback` to report a bug
3. Ask in the community Slack
