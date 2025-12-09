# Installation

## Recommended: pip

```bash
pip install jnkn
```

For full functionality (tree-sitter parsing, all language support):

```bash
pip install jnkn[full]
```

## Alternative Methods

=== "pipx (isolated)"

    ```bash
    pipx install jnkn[full]
    ```

=== "uv"

    ```bash
    uv tool install jnkn[full]
    ```

=== "Docker"

    ```bash
    docker pull ghcr.io/jnkn-io/jnkn:latest
    docker run --rm -v $(pwd):/app jnkn scan --dir /app
    ```

=== "From Source"

    ```bash
    git clone https://github.com/jnkn-io/jnkn.git
    cd jnkn
    pip install -e ".[full,dev]"
    ```

## Verify Installation

```bash
jnkn --version
```

Expected output:

```
jnkn 0.1.0
```

## Optional Dependencies

| Extra | What It Enables |
|-------|-----------------|
| `full` | Tree-sitter parsing, all language support |
| `dev` | Testing and development tools |

## Next Steps

[:octicons-arrow-right-24: Run your first scan](quickstart.md)
