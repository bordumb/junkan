# config.yaml Reference

Main configuration file at `.jnkn/config.yaml`.

## Full Schema

```yaml
# Jnkn Configuration

# Parsing settings
parsing:
  # File extensions to parse (auto-detected if not specified)
  extensions:
    python: [".py", ".pyi"]
    terraform: [".tf", ".tfvars"]
    kubernetes: [".yaml", ".yml"]
    javascript: [".js", ".ts", ".mjs"]
  
  # Python-specific settings
  python:
    # Additional extractors to load
    extra_extractors:
      - my_package.MyExtractor

# Stitching settings
stitching:
  # Minimum confidence for creating edges (0.0 - 1.0)
  min_confidence: 0.5
  
  # Token configuration
  min_token_length: 3
  
  # Tokens that provide no signal (ignored in matching)
  blocked_tokens:
    - id
    - key
    - url
    - host
    - port
  
  # Tokens that reduce confidence when matched alone
  low_value_tokens:
    - aws
    - prod
    - dev
    - main
    - test
  
  # Confidence calculation weights
  confidence:
    signals:
      exact_match: 1.0
      normalized_match: 0.9
      token_overlap_high: 0.85    # > 80% overlap
      token_overlap_medium: 0.7   # 50-80% overlap
      suffix_match: 0.6
      prefix_match: 0.6
      contains: 0.5
      single_token: 0.4
    
    penalties:
      short_token: 0.5      # Token < 4 chars
      common_token: 0.7     # Generic words
      ambiguous: 0.8        # Multiple possible matches
      low_value: 0.9        # Low-value tokens
  
  # Per-rule overrides
  rule_overrides:
    EnvVarToInfraRule:
      min_confidence: 0.6
      blocked_tokens:
        - host
    K8sToSecretRule:
      min_confidence: 0.4
  
  # Disable specific rules
  disabled_rules:
    - SomeUnwantedRule
  
  # Additional rules to load
  extra_rules:
    - my_package.MyRule

# Analysis settings
analysis:
  # Default max depth for blast radius (-1 = unlimited)
  default_max_depth: -1
  
  # Include transitive dependencies
  include_transitive: true

# Storage settings
storage:
  # Database path
  path: .jnkn/jnkn.db
  
  # Enable WAL mode for better concurrency
  wal_mode: true

# Output settings
output:
  # Default output format
  default_format: json
  
  # Include metadata in output
  include_metadata: true
  
  # Pretty print JSON
  pretty: true

# Logging
logging:
  level: INFO  # DEBUG, INFO, WARNING, ERROR
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Minimal Config

Most settings have sensible defaults. A minimal config:

```yaml
stitching:
  min_confidence: 0.5
```

## Section Reference

### `parsing`

Controls how files are discovered and parsed.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `extensions` | dict | auto | File extensions per language |
| `python.extra_extractors` | list | `[]` | Additional Python extractors |

### `stitching`

Controls how cross-domain links are created.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `min_confidence` | float | `0.5` | Minimum confidence threshold |
| `min_token_length` | int | `3` | Minimum token length |
| `blocked_tokens` | list | `[]` | Tokens to ignore |
| `low_value_tokens` | list | `[]` | Tokens that reduce confidence |
| `confidence.signals` | dict | see above | Signal weights |
| `confidence.penalties` | dict | see above | Penalty multipliers |
| `rule_overrides` | dict | `{}` | Per-rule settings |
| `disabled_rules` | list | `[]` | Rules to disable |
| `extra_rules` | list | `[]` | Additional rules to load |

### `analysis`

Controls blast radius and other analysis.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_max_depth` | int | `-1` | Default traversal depth |
| `include_transitive` | bool | `true` | Include transitive deps |

### `storage`

Controls the database.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `path` | string | `.jnkn/jnkn.db` | Database file path |
| `wal_mode` | bool | `true` | Enable WAL mode |

### `output`

Controls output formatting.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `default_format` | string | `json` | Default output format |
| `include_metadata` | bool | `true` | Include extra metadata |
| `pretty` | bool | `true` | Pretty print JSON |

### `logging`

Controls logging.

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `level` | string | `INFO` | Log level |
| `format` | string | see above | Log format string |
