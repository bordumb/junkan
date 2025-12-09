# Calculate Blast Radius

Find all artifacts impacted by a change.

## Basic Usage

```bash
jnkn blast <artifact-id>
```

## Artifact ID Formats

| Type | Format | Example |
|------|--------|---------|
| Environment variable | `env:NAME` | `env:DATABASE_URL` |
| File | `file://path` | `file://src/config.py` |
| Infrastructure | `infra:name` | `infra:aws_rds.main` |
| Kubernetes | `k8s:ns/kind/name` | `k8s:default/deployment/api` |
| dbt model | `data:model` | `data:fct_orders` |

## Options

### Limit Depth

Only show direct dependencies:

```bash
jnkn blast env:X --max-depth 1
```

Show up to 3 levels:

```bash
jnkn blast env:X --max-depth 3
```

### Multiple Sources

Analyze several artifacts at once:

```bash
jnkn blast env:DATABASE_URL env:REDIS_URL infra:aws_rds.main
```

### Filter by Type

Only show infrastructure impacts:

```bash
jnkn blast env:X --type infra
```

Only show code files:

```bash
jnkn blast env:X --type code
```

### Output Formats

=== "JSON (default)"

    ```bash
    jnkn blast env:X --format json
    ```

=== "Markdown"

    ```bash
    jnkn blast env:X --format markdown
    ```

=== "Plain"

    ```bash
    jnkn blast env:X --format plain
    ```

=== "SARIF"

    ```bash
    jnkn blast env:X --format sarif > results.sarif
    ```

## Scripting

### Check Impact Count

```bash
IMPACT=$(jnkn blast env:X --format json | jq '.total_impacted_count')

if [ "$IMPACT" -gt 10 ]; then
    echo "High impact: $IMPACT artifacts"
    exit 1
fi
```

### Get Impacted Files Only

```bash
jnkn blast env:X --format json | jq -r '.impacted_artifacts[]' | grep '^file://'
```

### Pipe to Other Tools

```bash
# Send to Slack
jnkn blast env:X --format markdown | slack-cli post "#alerts"

# Create Jira ticket
jnkn blast env:X --format json | jira-create-ticket.sh
```

## Understanding Results

```json
{
  "source_artifacts": ["env:DATABASE_URL"],
  "total_impacted_count": 5,
  "impacted_artifacts": [
    "file://src/db/connection.py",
    "file://src/api/users.py",
    "infra:aws_db_instance.main"
  ],
  "breakdown": {
    "code": ["file://src/db/connection.py", "file://src/api/users.py"],
    "infra": ["infra:aws_db_instance.main"],
    "env": [],
    "data": []
  },
  "max_depth_reached": 2
}
```

- `total_impacted_count`: Total number of affected artifacts
- `impacted_artifacts`: Full list of affected artifact IDs
- `breakdown`: Grouped by artifact type
- `max_depth_reached`: How many hops the deepest impact is

## Troubleshooting

### "Artifact not found"

The artifact ID may not exist in the graph. Check with:

```bash
jnkn stats --show-nodes | grep "DATABASE_URL"
```

### Results seem incomplete

Ensure you've scanned all relevant directories:

```bash
jnkn scan --dir . --full
```
