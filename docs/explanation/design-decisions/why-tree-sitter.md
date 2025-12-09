# Why Tree-Sitter

Rationale for our parsing technology choice.

## The Alternatives

| Approach | Pros | Cons |
|----------|------|------|
| **Regex** | Simple, fast | Misses context, false positives |
| **AST libraries** | Accurate | Language-specific, slow |
| **Tree-sitter** | Accurate, fast, universal | Learning curve |

## Why Not Regex?

Regex works for simple cases:

```python
# Matches
os.getenv("DATABASE_URL")
```

But fails on edge cases:

```python
# False positive: it's in a string
doc = 'Use os.getenv("DATABASE_URL")'

# False positive: it's a comment
# os.getenv("DATABASE_URL")

# False positive: different module
import mylib.os as os
os.getenv("NOT_STDLIB")

# Misses: multiline
os.getenv(
    "VALID_VAR"
)
```

Regex can't understand **context**.

## Why Not AST Libraries?

Python's `ast` module is accurate:

```python
import ast

tree = ast.parse(code)
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        # Check if it's os.getenv
        ...
```

But:

1. **Language-specific** — Need different code for Python, JavaScript, HCL
2. **Slow for large files** — Full parse required
3. **Fragile** — Syntax errors break entire parse

## Why Tree-Sitter

Tree-sitter provides:

### 1. Universal Query Language

One query syntax works across languages:

```scheme
; Python
(call
  function: (attribute object: (identifier) @obj)
  (#eq? @obj "os"))

; JavaScript (similar pattern)
(call_expression
  function: (member_expression object: (identifier) @obj)
  (#eq? @obj "process"))
```

### 2. Error Tolerance

Tree-sitter produces partial ASTs even with syntax errors:

```python
def broken(
    # Missing closing paren - tree-sitter still parses the rest

os.getenv("STILL_DETECTED")  # ✅ Found
```

### 3. Incremental Parsing

Only re-parse changed regions:

```python
# Change line 50 of a 1000-line file
# Tree-sitter: ~1ms
# Full re-parse: ~50ms
```

### 4. Performance

Tree-sitter is written in C with efficient memory usage:

| File Size | Tree-sitter | Python AST |
|-----------|-------------|------------|
| 100 lines | 0.5ms | 2ms |
| 1000 lines | 3ms | 20ms |
| 10000 lines | 25ms | 200ms |

## Trade-offs

### Learning Curve

Tree-sitter queries have unusual syntax:

```scheme
(call
  function: (attribute
    object: (identifier) @_obj
    attribute: (identifier) @_method)
  arguments: (argument_list (string) @env_var)
  (#eq? @_obj "os")
  (#eq? @_method "getenv"))
```

We mitigate this with:
- Pre-built queries for common patterns
- Regex fallback when tree-sitter isn't available
- Documentation and examples

### Dependency

Tree-sitter requires native binaries. We handle this by:
- Making it optional (`jnkn[full]`)
- Falling back to regex when unavailable
- Providing pre-built Docker images

## The Result

Tree-sitter enables Jnkn to:

1. **Parse accurately** — Context-aware pattern detection
2. **Handle errors** — Graceful degradation on syntax issues
3. **Scale** — Fast parsing for large codebases
4. **Extend** — Same query language for new languages
