# Compare Branches

Analyze dependency changes between git refs.

## Basic Usage

```bash
jnkn diff main..feature-branch
```

## How It Works

1. Checks out base ref, scans to temporary database
2. Checks out target ref, scans to another database
3. Compares graphs and reports differences

## Output

```json
{
  "added_nodes": [
    {"id": "env:NEW_VAR", "type": "env_var"}
  ],
  "removed_nodes": [
    {"id": "env:OLD_VAR", "type": "env_var"}
  ],
  "added_edges": [
    {"source": "file://src/new.py", "target": "env:NEW_VAR"}
  ],
  "removed_edges": [
    {"source": "file://src/old.py", "target": "env:OLD_VAR"}
  ],
  "summary": {
    "nodes_added": 1,
    "nodes_removed": 1,
    "edges_added": 1,
    "edges_removed": 1
  }
}
```

## Compare with Working Directory

Compare current state against a branch:

```bash
jnkn diff main
```

## CI Integration

```yaml
- name: Compare with main
  run: |
    DIFF=$(jnkn diff origin/main --format json)
    ADDED=$(echo "$DIFF" | jq '.summary.nodes_added')
    REMOVED=$(echo "$DIFF" | jq '.summary.nodes_removed')
    
    echo "Added $ADDED nodes, removed $REMOVED nodes"
```

## Focus on Specific Changes

### New Dependencies Only

```bash
jnkn diff main --show added
```

### Removed Dependencies Only

```bash
jnkn diff main --show removed
```

### Filter by Type

```bash
jnkn diff main --type env_var
```

## Markdown Report

```bash
jnkn diff main --format markdown
```

Output:

```markdown
## Dependency Changes: main → HEAD

### Added (3)
| Type | Artifact |
|------|----------|
| env_var | env:NEW_API_KEY |
| code_file | file://src/api/v2.py |
| edge | src/api/v2.py → NEW_API_KEY |

### Removed (1)
| Type | Artifact |
|------|----------|
| env_var | env:DEPRECATED_VAR |
```

## Performance

Diff requires scanning both branches. For large repos, this can be slow.

Tips:

- Use `--dir` to limit scope
- Cache base branch database in CI
- Run only on relevant file changes
