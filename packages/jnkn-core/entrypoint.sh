#!/bin/bash
set -e

# 1. FIX DUBIOUS OWNERSHIP (CRITICAL FIX)
# GitHub Actions overrides HOME to /github/home, so build-time config is ignored.
# We must set this at runtime before running any git commands.
git config --global --add safe.directory /github/workspace

# 2. FETCH BASE REF
# GITHUB_BASE_REF is set by Actions for Pull Requests (e.g., "main")
if [[ -n "$GITHUB_BASE_REF" ]]; then
    echo "📥 Fetching base ref: origin/$GITHUB_BASE_REF"
    # Fetch the specific branch so the diff engine has a comparison target
    git -C /github/workspace fetch origin "$GITHUB_BASE_REF" --depth=1 || {
        echo "⚠️  Fetch failed. 'jnkn check' may fail if it cannot find the base ref."
    }
fi

# 3. RUN CLI
exec jnkn "$@"