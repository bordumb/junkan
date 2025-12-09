# Export Results

Export Jnkn results in various formats for integration with other tools.

## JSON Export

Default format, suitable for scripting:

```bash
jnkn blast env:X --format json > results.json
```

```bash
jnkn stats --format json > stats.json
```

## SARIF Export

For IDE integration and GitHub Advanced Security:

```bash
jnkn blast env:X --format sarif > jnkn.sarif
```

Upload to GitHub:

```yaml
- name: Upload SARIF
  uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: jnkn.sarif
```

## CSV Export

For spreadsheet analysis:

```bash
jnkn stats --nodes --format csv > nodes.csv
jnkn stats --edges --format csv > edges.csv
```

## GraphML Export

For visualization in tools like Gephi or yEd:

```bash
jnkn export --format graphml > graph.graphml
```

## DOT Export

For Graphviz visualization:

```bash
jnkn export --format dot > graph.dot
dot -Tpng graph.dot -o graph.png
```

## Export Full Graph

Export all nodes and edges:

```bash
jnkn export --format json > full-graph.json
```

Structure:

```json
{
  "nodes": [
    {"id": "env:DATABASE_URL", "type": "env_var", "metadata": {...}},
    ...
  ],
  "edges": [
    {"source": "file://src/app.py", "target": "env:DATABASE_URL", "type": "reads"},
    ...
  ]
}
```

## Filter Exports

Export only certain types:

```bash
jnkn export --type env_var --format json > env-vars.json
jnkn export --type infra --format json > infrastructure.json
```

## Pipe to Other Tools

```bash
# Pretty print
jnkn blast env:X | jq .

# Count impacted files
jnkn blast env:X | jq '.impacted_artifacts | length'

# Get unique impacted types
jnkn blast env:X | jq -r '.breakdown | keys[]'
```
