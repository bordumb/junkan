#!/bin/bash

# scripts/serve_docs.sh
# Serves documentation locally at http://127.0.0.1:8000

set -e

echo "📖 Starting local documentation server..."

# Ensure docs dependencies are available and serve
uv run --extra docs mkdocs serve