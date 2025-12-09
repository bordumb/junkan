# CI Integration

Add Jnkn to your CI pipeline to catch breaking changes on every PR.

## GitHub Actions

Create `.github/workflows/jnkn.yml`:

```yaml
name: Jnkn Impact Analysis

on:
  pull_request:
    paths:
      - '**.py'
      - '**.tf'
      - '**/dbt/**'

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Need history for diff
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install Jnkn
        run: pip install jnkn[full]
      
      - name: Scan codebase
        run: jnkn scan
      
      - name: Analyze changed files
        run: |
          # Get changed files
          CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD | grep -E '\.(py|tf)$' || true)
          
          if [ -n "$CHANGED" ]; then
            echo "## 🔍 Impact Analysis" >> $GITHUB_STEP_SUMMARY
            for file in $CHANGED; do
              echo "### $file" >> $GITHUB_STEP_SUMMARY
              jnkn blast "file://$file" --format markdown >> $GITHUB_STEP_SUMMARY 2>/dev/null || true
            done
          fi
```

## What This Does

1. **Triggers** on PRs that modify Python or Terraform files
2. **Scans** your codebase to build the dependency graph
3. **Analyzes** each changed file's blast radius
4. **Reports** results in the GitHub Actions summary

## Example Output

When a PR modifies `terraform/rds.tf`:

```markdown
## 🔍 Impact Analysis

### terraform/rds.tf

**Blast Radius: 5 artifacts**

| Type | Artifact | Confidence |
|------|----------|------------|
| env_var | env:DATABASE_URL | 0.92 |
| code_file | src/db/connection.py | 0.88 |
| code_file | src/api/users.py | 0.85 |
```

## Block on High-Risk Changes

Add a failure condition for high-impact changes:

```yaml
- name: Check impact threshold
  run: |
    IMPACT=$(jnkn blast "file://$FILE" --format json | jq '.total_impacted')
    if [ "$IMPACT" -gt 10 ]; then
      echo "::error::High impact change: $IMPACT artifacts affected"
      exit 1
    fi
```

## GitLab CI

See [GitLab CI Integration](../how-to/integration/gitlab-ci.md) for GitLab-specific setup.

## Next Steps

- [:octicons-arrow-right-24: Configure confidence thresholds](../how-to/configuration/configure-confidence.md)
- [:octicons-arrow-right-24: Manage suppressions](../how-to/configuration/manage-suppressions.md)
