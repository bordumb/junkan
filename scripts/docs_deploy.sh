#!/bin/bash

# scripts/deploy_docs.sh
# Builds and deploys documentation to GitHub Pages.

set -e

echo "🚀 Deploying documentation to GitHub Pages..."

# Ensure we have the docs dependencies and deploy
uv run --extra docs mkdocs gh-deploy --force

echo "✅ Docs deployed!"