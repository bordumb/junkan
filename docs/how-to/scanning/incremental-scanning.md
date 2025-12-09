# Incremental Scanning

Only re-scan files that have changed since the last scan.

## How It Works

Jnkn stores a hash of each file. On subsequent scans, unchanged files are skipped:

```
First scan:  847 files parsed
Second scan: 12 files parsed (835 unchanged)
```

## Usage

Incremental scanning is **automatic**:

```bash
jnkn scan  # First time: full scan
# ... make changes ...
jnkn scan  # Only changed files
```

## Force Full Rescan

When you need to regenerate everything:

```bash
jnkn scan --full
```

Use this when:

- Upgrading Jnkn (new patterns detected)
- Changing configuration
- Debugging issues

## Check File Status

See which files would be scanned:

```bash
jnkn scan --dry-run
```

```
Would scan:
  src/config.py (modified)
  src/api/users.py (modified)
  terraform/rds.tf (new)

Would skip:
  src/main.py (unchanged)
  src/utils.py (unchanged)
  ... 842 more unchanged files
```

## Git Integration

Scan only files changed in a PR:

```bash
# Get changed files from git
CHANGED=$(git diff --name-only origin/main...HEAD)

# Scan just those files
jnkn scan --files $CHANGED
```

Or in CI:

```yaml
- name: Scan changed files
  run: |
    CHANGED=$(git diff --name-only ${{ github.event.before }} ${{ github.sha }})
    jnkn scan --files $CHANGED
```

## Cache Location

The database is stored at `.jnkn/jnkn.db` by default.

To use a different location:

```bash
jnkn scan --db /path/to/jnkn.db
```

## Troubleshooting

### Files not being detected as changed

Check the stored hash:

```bash
jnkn stats --show-hashes | grep myfile.py
```

### Scan is slow despite few changes

The stitching phase runs on all nodes, not just changed files. This is necessary to detect new cross-domain links.

For very large graphs, consider splitting by domain (see [Scan a Monorepo](scan-monorepo.md)).
