#!/bin/bash
set -e

# Fetch the base ref so origin/main (or whatever base) exists
# GITHUB_BASE_REF is automatically set by GitHub Actions for PRs
if [[ -n "$GITHUB_BASE_REF" ]]; then
    echo "📥 Fetching base ref: origin/$GITHUB_BASE_REF"
    git -C /github/workspace fetch origin "$GITHUB_BASE_REF":refs/remotes/origin/"$GITHUB_BASE_REF" 2>/dev/null || {
        echo "⚠️  Fetch with refspec failed, trying simple fetch..."
        git -C /github/workspace fetch origin "$GITHUB_BASE_REF" || true
    }
fi

# Now run jnkn with all the arguments passed to this script
exec jnkn "$@"