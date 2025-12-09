# .jnknignore Reference

Exclude files and directories from scanning.

## Location

Place `.jnknignore` in your project root (same level as `.jnkn/`).

## Syntax

Uses gitignore-style patterns.

```gitignore
# Comments start with #

# Ignore specific file
secret.py

# Ignore by extension
*.test.py
*_test.go

# Ignore directories
node_modules/
vendor/
__pycache__/
.git/

# Ignore paths
tests/fixtures/
docs/

# Negate (un-ignore)
!important.test.py

# Wildcards
*.min.js
build-*

# Double star (any depth)
**/generated/**
```

## Pattern Reference

| Pattern | Matches | Doesn't Match |
|---------|---------|---------------|
| `*.py` | `foo.py`, `dir/bar.py` | `foo.pyc` |
| `test_*.py` | `test_foo.py` | `foo_test.py` |
| `tests/` | `tests/foo.py` | `src/tests.py` |
| `**/test/**` | `a/test/b.py`, `test/c.py` | `testing/d.py` |
| `!important.py` | (negates previous rule) | |

## Default Ignores

Even without `.jnknignore`, Jnkn skips:

```
.git/
.hg/
.svn/
__pycache__/
*.pyc
*.pyo
node_modules/
.terraform/
```

## Examples

### Python Project

```gitignore
# Virtual environments
venv/
.venv/
env/

# Caches
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/

# Tests (optional - you may want to scan these)
tests/
*_test.py
test_*.py

# Generated
*.egg-info/
dist/
build/
```

### Terraform Project

```gitignore
# State files
*.tfstate
*.tfstate.backup

# Terraform internals
.terraform/
.terraform.lock.hcl

# Environment-specific
environments/dev/
environments/staging/
```

### Monorepo

```gitignore
# Third-party
vendor/
node_modules/

# Generated code
**/generated/
**/*.pb.go

# Documentation
docs/

# Specific services to skip
services/deprecated-*/
```

## Precedence

1. Built-in defaults (lowest)
2. `.jnknignore` in project root
3. `--exclude` CLI flag (highest)

## Debugging

See what's being ignored:

```bash
jnkn scan --verbose
```

Output shows:

```
Ignored: tests/test_foo.py (matched: tests/)
Ignored: build/output.py (matched: build/)
Scanning: src/main.py
```
