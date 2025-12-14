#!/bin/bash
set -e

# 1. FIX DUBIOUS OWNERSHIP
# This must run before any other git command because the workspace 
# is mounted from the host (runner) but we are running as root (container).
git config --global --add safe.directory /github/workspace

# 2. FETCH BASE REF
# GITHUB_BASE_REF is set by Actions for Pull Requests (e.g., "main")
# We need to fetch it so that 'git diff origin/main...HEAD' works.
if [[ -n "$GITHUB_BASE_REF" ]]; then
    echo "📥 Fetching base ref: origin/$GITHUB_BASE_REF"
    
    # Try fetching the specific branch to origin/BRANCH_NAME
    # We suppress stderr to avoid confusing logs if it fails, but retry safely
    git -C /github/workspace fetch origin "$GITHUB_BASE_REF":refs/remotes/origin/"$GITHUB_BASE_REF" --depth=1 2>/dev/null || {
        echo "⚠️  Fetch with refspec failed, trying simple fetch..."
        git -C /github/workspace fetch origin "$GITHUB_BASE_REF" --depth=1
    }
fi

# 3. RUN THE CLI
# Pass all arguments through to the jnkn CLI
exec jnkn "$@"