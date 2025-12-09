# Development Setup

Set up a local development environment.

## Prerequisites

- Python 3.11+
- Git
- (Optional) Docker

## Clone Repository

```bash
git clone https://github.com/jnkn-io/jnkn.git
cd jnkn
```

## Install Dependencies

### Using pip

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install with all dependencies
pip install -e ".[full,dev]"
```

### Using uv (Recommended)

```bash
uv venv
source .venv/bin/activate
uv pip install -e ".[full,dev]"
```

## Verify Installation

```bash
# CLI works
jnkn --version

# Tests pass
pytest tests/unit/ -v

# Linter passes
ruff check .
```

## Project Structure

```
jnkn/
├── src/jnkn/           # Main package
│   ├── cli/              # CLI commands
│   ├── core/             # Core types, graph, storage
│   ├── parsing/          # Language parsers
│   │   ├── python/
│   │   ├── terraform/
│   │   └── kubernetes/
│   ├── stitching/        # Cross-domain linking
│   └── analysis/         # Blast radius, explain, diff
├── tests/
│   ├── unit/             # Unit tests
│   ├── integration/      # Integration tests
│   └── e2e/              # End-to-end tests
├── docs/                 # Documentation
└── pyproject.toml        # Project configuration
```

## Running Tests

```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Specific test file
pytest tests/unit/test_confidence.py

# With coverage
pytest --cov=jnkn --cov-report=html
open htmlcov/index.html
```

## Running Linter

```bash
# Check
ruff check .

# Fix automatically
ruff check --fix .

# Format
ruff format .
```

## Building Documentation

```bash
# Install docs dependencies
pip install mkdocs-material mkdocstrings[python]

# Serve locally
mkdocs serve

# Build
mkdocs build
```

## IDE Setup

### VS Code

Recommended extensions:
- Python
- Ruff
- Even Better TOML

Settings (`.vscode/settings.json`):

```json
{
  "python.defaultInterpreterPath": ".venv/bin/python",
  "python.testing.pytestEnabled": true,
  "editor.formatOnSave": true,
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff"
  }
}
```

### PyCharm

- Set Project Interpreter to `.venv`
- Enable pytest as test runner
- Configure Ruff as external tool

## Troubleshooting

### Tree-sitter not found

```bash
pip install tree-sitter tree-sitter-languages
```

### Tests fail with import error

```bash
pip install -e ".[full,dev]"
```

### Permission denied on scripts

```bash
chmod +x scripts/*.sh
```
