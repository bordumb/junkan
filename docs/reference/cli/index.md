# CLI Reference

## Global Options

```bash
jnkn [OPTIONS] COMMAND [ARGS]
```

| Option | Description |
|--------|-------------|
| `--db PATH` | Database path (default: `.jnkn/jnkn.db`) |
| `--config PATH` | Config file (default: `.jnkn/config.yaml`) |
| `--verbose` | Enable verbose output |
| `--quiet` | Suppress non-error output |
| `--version` | Show version |
| `--help` | Show help |

## Commands

### `jnkn init`

Initialize Jnkn in the current directory.

```bash
jnkn init [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--force` | Overwrite existing configuration |

Creates:
- `.jnkn/config.yaml`
- `.jnkn/suppressions.yaml`
- `.jnknignore`

---

### `jnkn scan`

Parse codebase and build dependency graph.

```bash
jnkn scan [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--dir PATH` | `.` | Directory to scan |
| `--full` | `false` | Force full rescan |
| `--jobs N` | `1` | Parallel workers |
| `--files FILE...` | | Scan specific files only |

Examples:

```bash
jnkn scan
jnkn scan --dir src/ --dir terraform/
jnkn scan --full --jobs 4
```

---

### `jnkn blast-radius`

Calculate downstream impact.

```bash
jnkn blast ARTIFACT [ARTIFACTS...] [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--max-depth N` | `-1` | Max traversal depth (-1 = unlimited) |
| `--type TYPE` | | Filter by artifact type |
| `--format FMT` | `json` | Output format: json, markdown, plain, sarif |

Examples:

```bash
jnkn blast env:DATABASE_URL
jnkn blast env:X env:Y --max-depth 2
jnkn blast env:X --format markdown
```

---

### `jnkn explain`

Explain why a match was made (or not made).

```bash
jnkn explain SOURCE TARGET [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--why-not` | Explain why match was rejected |
| `--alternatives` | Show other candidates considered |

Examples:

```bash
jnkn explain env:DB_HOST infra:db_host
jnkn explain env:HOST infra:main --why-not
```

---

### `jnkn suppress`

Manage suppressions.

```bash
jnkn suppress COMMAND [OPTIONS]
```

#### `suppress add`

```bash
jnkn suppress add SOURCE_PATTERN TARGET_PATTERN [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--reason TEXT` | Reason for suppression |
| `--expires DATE` | Expiration date (ISO format) |

#### `suppress list`

```bash
jnkn suppress list [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--format FMT` | Output format: table, json, yaml |

#### `suppress remove`

```bash
jnkn suppress remove ID
jnkn suppress remove --source PATTERN --target PATTERN
```

#### `suppress test`

```bash
jnkn suppress test SOURCE TARGET
```

---

### `jnkn stats`

Show graph statistics.

```bash
jnkn stats [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--nodes` | Show all nodes |
| `--edges` | Show all edges |
| `--format FMT` | Output format: table, json |

---

### `jnkn diff`

Compare dependency graphs between git refs.

```bash
jnkn diff [REF1]..[REF2] [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--show WHAT` | Show: all, added, removed |
| `--type TYPE` | Filter by artifact type |
| `--format FMT` | Output format: json, markdown |

Examples:

```bash
jnkn diff main..HEAD
jnkn diff main --show added
```

---

### `jnkn export`

Export the dependency graph.

```bash
jnkn export [OPTIONS]
```

| Option | Default | Description |
|--------|---------|-------------|
| `--format FMT` | `json` | Format: json, graphml, dot, csv |
| `--type TYPE` | | Filter by artifact type |

---

### `jnkn clear`

Clear all data.

```bash
jnkn clear [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `JUNKAN_DB` | Database path |
| `JUNKAN_CONFIG` | Config file path |
| `JUNKAN_MIN_CONFIDENCE` | Override confidence threshold |
| `JUNKAN_LOG_LEVEL` | Logging level: DEBUG, INFO, WARNING, ERROR |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Parse error |
| 10 | Impact threshold exceeded (CI mode) |
