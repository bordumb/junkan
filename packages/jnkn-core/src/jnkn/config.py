"""
Global Configuration and Safety Defaults.

This module centralizes the "Safe Defaults" derived from repository forensics.
It protects the parser engine from binary files, massive generated code,
and infinite recursion loops.
"""

from pathlib import Path
from typing import Set

# --- Safety Limits ---
# Files larger than this are skipped to prevent memory exhaustion
MAX_FILE_SIZE_BYTES = 500 * 1024  # 500KB (Conservative default)

# Lines longer than this often crash regex engines (minified code)
MAX_LINE_LENGTH = 10_000

# Maximum directory depth to prevent stack overflows in recursive walkers
MAX_DIRECTORY_DEPTH = 15

# --- Blocklists ---

# Directories to completely ignore during traversal (Recursion/Perf Safety)
IGNORE_DIRECTORIES: Set[str] = {
    # Version Control
    ".git",
    ".svn",
    ".hg",
    # Environments & Dependencies
    ".venv",
    "venv",
    "env",
    ".env",
    "node_modules",
    "target",
    "build",
    "dist",
    "out",
    "bin",
    "site-packages",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    # IDEs
    ".idea",
    ".vscode",
    # Testing & Generated Data
    "__snapshots__",
    "__mocks__",
    "coverage",
    "htmlcov",
    "fixtures",
    # Jnkn internal
    ".jnkn",
}

# Extensions that look like text but are binaries or data dumps (Encoding Safety)
BINARY_EXTENSIONS: Set[str] = {
    # Images/Media
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".mp4",
    ".mov",
    ".webp",
    # Archives/Binary Code
    ".zip",
    ".tar",
    ".gz",
    ".pyc",
    ".pyo",
    ".so",
    ".dll",
    ".exe",
    ".bin",
    ".whl",
    ".deb",
    ".rpm",
    # Data Science/Docs (Added from Forensics)
    ".pdf",
    ".inv",
    ".pkl",
    ".parquet",
    ".npy",
    ".h5",
    ".onnx",
    ".pb",
    # Terraform State/Plan (Binary or Huge JSON)
    ".tfstate",
    ".tfstate.backup",
    ".tfplan",
    # Source Maps (Huge single-line JSON)
    ".map",
}

# Files to skip based on pattern matching (Noise Reduction)
IGNORE_FILE_PATTERNS: Set[str] = {
    # Locks
    "*.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Gemfile.lock",
    # Minified Code
    "*.min.js",
    "*.min.css",
    # Logs
    "*.log",
    # Test Artifacts
    "*.snap",
    ".test_durations",
}


def is_binary_extension(path: Path) -> bool:
    """Check if file extension is in the blocklist."""
    return path.suffix.lower() in BINARY_EXTENSIONS


def is_ignored_directory(dir_name: str) -> bool:
    """Check if directory name is in the blocklist."""
    return dir_name in IGNORE_DIRECTORIES
