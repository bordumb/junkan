# Scan a Monorepo

Strategies for scanning large codebases efficiently.

## The Challenge

Monorepos can have thousands of files. A full scan may take minutes and produce a huge graph.

## Strategy 1: Scope to Directories

Scan only relevant directories:

```bash
jnkn scan --dir src/services --dir terraform/
```

Or use `.jnknignore`:

```gitignore
# .jnknignore
node_modules/
vendor/
*.test.py
*_test.go
__pycache__/
.git/
docs/
scripts/
```

## Strategy 2: Incremental Scanning

Only re-scan changed files:

```bash
# First scan (full)
jnkn scan

# Subsequent scans (incremental)
jnkn scan  # Automatically detects unchanged files via hash
```

Force full rescan if needed:

```bash
jnkn scan --full
```

## Strategy 3: Parallel Scanning

Use multiple cores:

```bash
jnkn scan --jobs 8
```

Or auto-detect:

```bash
jnkn scan --jobs auto  # Uses CPU count
```

## Strategy 4: Split by Domain

For very large monorepos, maintain separate databases:

```bash
# Backend team
jnkn scan --dir backend/ --db .jnkn/backend.db

# Infrastructure team  
jnkn scan --dir terraform/ --db .jnkn/infra.db

# Query across both
jnkn blast env:DATABASE_URL \
  --db .jnkn/backend.db \
  --db .jnkn/infra.db
```

## Strategy 5: CI Caching

Cache the database between CI runs:

```yaml
- uses: actions/cache@v4
  with:
    path: .jnkn/
    key: jnkn-${{ hashFiles('**/*.py', '**/*.tf') }}
    restore-keys: jnkn-
```

## Performance Tips

| Files | Expected Scan Time | Recommendation |
|-------|-------------------|----------------|
| < 100 | < 5 seconds | Default settings |
| 100-1000 | 5-30 seconds | Enable caching |
| 1000-10000 | 30s - 3 min | Parallel + incremental |
| > 10000 | 3+ min | Split by domain |

## Monitoring Scan Performance

```bash
jnkn scan --verbose
```

Output includes timing:

```
Parsing: 12.3s (847 files)
Stitching: 3.2s (156 rules evaluated)
Storage: 0.8s (2341 nodes written)
Total: 16.3s
```
