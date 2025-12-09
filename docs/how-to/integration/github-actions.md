# GitHub Actions

Set up Jnkn in GitHub Actions CI/CD.

## Minimal Setup

```yaml
name: Jnkn
on: [pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install jnkn[full]
      - run: jnkn scan
      - run: jnkn stats
```

## With PR Comments

```yaml
name: Jnkn Impact Analysis
on:
  pull_request:
    paths: ['**.py', '**.tf', '**.yaml']

permissions:
  contents: read
  pull-requests: write

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'pip'
      
      - run: pip install jnkn[full]
      
      - name: Scan and analyze
        id: jnkn
        run: |
          jnkn scan
          
          # Analyze changed files
          CHANGED=$(git diff --name-only origin/${{ github.base_ref }}...HEAD | grep -E '\.(py|tf)$' || true)
          
          if [ -n "$CHANGED" ]; then
            REPORT=$(mktemp)
            for f in $CHANGED; do
              echo "### \`$f\`" >> $REPORT
              jnkn blast "file://$f" --format markdown >> $REPORT 2>/dev/null || echo "No dependencies" >> $REPORT
            done
            echo "report<<EOF" >> $GITHUB_OUTPUT
            cat $REPORT >> $GITHUB_OUTPUT
            echo "EOF" >> $GITHUB_OUTPUT
          fi
      
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            const report = `${{ steps.jnkn.outputs.report }}`;
            if (report) {
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: `## 🔍 Jnkn Impact Analysis\n\n${report}`
              });
            }
```

## With Caching

```yaml
- uses: actions/cache@v4
  with:
    path: .jnkn/
    key: jnkn-${{ runner.os }}-${{ hashFiles('**/*.py', '**/*.tf') }}
    restore-keys: |
      jnkn-${{ runner.os }}-
```

## Block on High Impact

```yaml
- name: Check impact threshold
  run: |
    MAX_IMPACT=10
    
    for f in $(git diff --name-only origin/main...HEAD | grep -E '\.(py|tf)$'); do
      IMPACT=$(jnkn blast "file://$f" --format json 2>/dev/null | jq '.total_impacted_count // 0')
      if [ "$IMPACT" -gt "$MAX_IMPACT" ]; then
        echo "::error file=$f::High impact ($IMPACT) exceeds threshold ($MAX_IMPACT)"
        exit 1
      fi
    done
```

## Matrix Strategy

Scan different components in parallel:

```yaml
jobs:
  analyze:
    strategy:
      matrix:
        component: [backend, frontend, infrastructure]
    steps:
      - run: jnkn scan --dir ${{ matrix.component }}/
```

## Reusable Workflow

Create `.github/workflows/jnkn-reusable.yml`:

```yaml
name: Jnkn Reusable
on:
  workflow_call:
    inputs:
      directory:
        type: string
        default: '.'
      threshold:
        type: number
        default: 10

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install jnkn[full]
      - run: jnkn scan --dir ${{ inputs.directory }}
```

Use in other workflows:

```yaml
jobs:
  jnkn:
    uses: ./.github/workflows/jnkn-reusable.yml
    with:
      directory: src/
      threshold: 5
```
