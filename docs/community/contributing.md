# Contributing

Thank you for your interest in contributing to Jnkn!

## Quick Start

```bash
# Clone
git clone https://github.com/jnkn-io/jnkn.git
cd jnkn

# Install with dev dependencies
pip install -e ".[full,dev]"

# Run tests
pytest

# Run linter
ruff check .
```

## Development Workflow

### 1. Find or Create an Issue

- Check [existing issues](https://github.com/jnkn-io/jnkn/issues)
- For new features, open a discussion first
- Comment on an issue to claim it

### 2. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-number-description
```

### 3. Make Changes

- Write code
- Add tests
- Update documentation

### 4. Test

```bash
# Run all tests
pytest

# Run specific tests
pytest tests/unit/test_confidence.py

# Run with coverage
pytest --cov=jnkn
```

### 5. Lint

```bash
# Check
ruff check .

# Fix automatically
ruff check --fix .

# Format
ruff format .
```

### 6. Submit PR

- Push your branch
- Open a Pull Request
- Fill out the PR template
- Wait for review

## What to Contribute

### Good First Issues

Look for issues labeled `good first issue`:

- Documentation improvements
- Test coverage
- Small bug fixes

### Larger Contributions

For bigger changes, discuss first:

- New language parsers
- New stitching rules
- Performance improvements
- New output formats

## Code Style

- **Python 3.11+** — Use modern syntax
- **Type hints** — All public functions
- **Docstrings** — Google style
- **Tests** — Aim for 90%+ coverage

### Example

```python
def calculate_confidence(
    source_tokens: list[str],
    target_tokens: list[str],
) -> float:
    """
    Calculate match confidence between token sets.
    
    Args:
        source_tokens: Tokens from source artifact.
        target_tokens: Tokens from target artifact.
    
    Returns:
        Confidence score between 0.0 and 1.0.
    
    Example:
        >>> calculate_confidence(["database", "url"], ["database", "url"])
        0.9
    """
    ...
```

## Documentation

Documentation lives in `docs/`. We use MkDocs Material.

### Preview Locally

```bash
pip install mkdocs-material
mkdocs serve
# Open http://localhost:8000
```

### Guidelines

- Be concise
- Include examples
- Update relevant pages when changing features

## Questions?

- Open a GitHub Discussion
- Ask in Slack
- Email maintainers@jnkn.io
