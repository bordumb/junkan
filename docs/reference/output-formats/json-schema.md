# JSON Output Schema

Reference for Jnkn's JSON output formats.

## Blast Radius

```bash
jnkn blast env:DATABASE_URL --format json
```

```json
{
  "source_artifacts": ["env:DATABASE_URL"],
  "total_impacted_count": 5,
  "impacted_artifacts": [
    "file://src/db/connection.py",
    "file://src/api/users.py",
    "infra:aws_db_instance.main",
    "k8s:default/deployment/api",
    "k8s:default/secret/db-creds"
  ],
  "breakdown": {
    "code": [
      "file://src/db/connection.py",
      "file://src/api/users.py"
    ],
    "infra": [
      "infra:aws_db_instance.main"
    ],
    "k8s": [
      "k8s:default/deployment/api",
      "k8s:default/secret/db-creds"
    ],
    "env": [],
    "data": []
  },
  "max_depth_reached": 2,
  "paths": [
    {
      "target": "file://src/db/connection.py",
      "path": ["env:DATABASE_URL", "file://src/db/connection.py"],
      "depth": 1
    }
  ]
}
```

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `source_artifacts` | string[] | Input artifact IDs |
| `total_impacted_count` | integer | Total downstream artifacts |
| `impacted_artifacts` | string[] | All impacted artifact IDs |
| `breakdown` | object | Artifacts grouped by type |
| `max_depth_reached` | integer | Deepest traversal level |
| `paths` | object[] | (Optional) Paths to each artifact |

## Stats

```bash
jnkn stats --format json
```

```json
{
  "version": "0.1.0",
  "schema_version": 2,
  "database_path": ".jnkn/jnkn.db",
  "database_size_bytes": 124500,
  "total_nodes": 156,
  "total_edges": 97,
  "tracked_files": 47,
  "nodes_by_type": {
    "code_file": 42,
    "env_var": 12,
    "infra_resource": 8,
    "k8s_resource": 6
  },
  "edges_by_type": {
    "reads": 45,
    "imports": 32,
    "provides": 12,
    "configures": 8
  },
  "cross_domain_edges": 8,
  "last_scan": "2024-01-15T10:30:00Z"
}
```

## Explain

```bash
jnkn explain env:DB_HOST infra:db_host --format json
```

```json
{
  "source": {
    "id": "env:DB_HOST",
    "type": "env_var",
    "tokens": ["db", "host"]
  },
  "target": {
    "id": "infra:db_host",
    "type": "infra_resource",
    "tokens": ["db", "host"]
  },
  "confidence": {
    "score": 0.85,
    "level": "HIGH",
    "signals": [
      {
        "name": "normalized_match",
        "weight": 0.9,
        "description": "'dbhost' == 'dbhost'"
      }
    ],
    "penalties": [
      {
        "name": "short_token",
        "multiplier": 0.95,
        "description": "Token 'db' is only 2 chars"
      }
    ]
  },
  "matched_tokens": ["db", "host"],
  "would_create_edge": true,
  "suppressed": false
}
```

## Diff

```bash
jnkn diff main..HEAD --format json
```

```json
{
  "base_ref": "main",
  "target_ref": "HEAD",
  "summary": {
    "nodes_added": 3,
    "nodes_removed": 1,
    "edges_added": 5,
    "edges_removed": 2
  },
  "added_nodes": [
    {
      "id": "env:NEW_VAR",
      "type": "env_var",
      "metadata": {
        "file": "src/config.py",
        "line": 15
      }
    }
  ],
  "removed_nodes": [
    {
      "id": "env:OLD_VAR",
      "type": "env_var"
    }
  ],
  "added_edges": [
    {
      "source": "file://src/new.py",
      "target": "env:NEW_VAR",
      "type": "reads"
    }
  ],
  "removed_edges": [
    {
      "source": "file://src/old.py",
      "target": "env:OLD_VAR",
      "type": "reads"
    }
  ]
}
```

## Export (Full Graph)

```bash
jnkn export --format json
```

```json
{
  "version": "0.1.0",
  "exported_at": "2024-01-15T10:30:00Z",
  "nodes": [
    {
      "id": "env:DATABASE_URL",
      "name": "DATABASE_URL",
      "type": "env_var",
      "metadata": {
        "source": "os.getenv",
        "file": "src/config.py",
        "line": 10
      }
    },
    {
      "id": "file://src/config.py",
      "name": "config.py",
      "type": "code_file",
      "path": "src/config.py",
      "language": "python",
      "file_hash": "abc123..."
    }
  ],
  "edges": [
    {
      "source": "file://src/config.py",
      "target": "env:DATABASE_URL",
      "type": "reads",
      "metadata": {
        "pattern": "os.getenv",
        "confidence": 1.0
      }
    }
  ]
}
```

## Node Types

| Type | Description |
|------|-------------|
| `code_file` | Source code file |
| `code_entity` | Function/class definition |
| `env_var` | Environment variable |
| `infra_resource` | Terraform resource |
| `k8s_resource` | Kubernetes resource |
| `data_asset` | dbt model/source |
| `unknown` | Unresolved reference |

## Edge Types

| Type | Description |
|------|-------------|
| `reads` | Source reads from target |
| `imports` | Source imports target |
| `provides` | Source provides target |
| `configures` | Source configures target |
| `contains` | Source contains target |
| `references` | Generic reference |
