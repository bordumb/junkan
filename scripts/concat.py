#!/usr/bin/env python3
"""
Recursively scans a repository and concatenates text files into a single output file,
with robust filtering for binaries, large files, noisy artifacts, and optional
master include scoping.
"""

import os
from pathlib import Path

# ------------------------------------------------------------
# MASTER INCLUDE FILTER (OPTIONAL)
# ------------------------------------------------------------
# If empty: scan entire repo (default behavior)
# If non-empty: ONLY include files under these paths (relative to repo root)
#
# Examples:
# MASTER_INCLUDE_PATHS = ["src/jnkn/parsing"]
#
MASTER_INCLUDE_PATHS = ["packages"]

# ------------------------------------------------------------
# CONFIGURATION
# ------------------------------------------------------------

# Skip files larger than this (e.g., 500KB) to save context window
MAX_FILE_SIZE_BYTES = 500 * 1024

DEFAULT_IGNORE_FILES = {
    # Lock files (noisy context)
    "poetry.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "Cargo.lock",
    "uv.lock",
    "Gemfile.lock",
    "go.sum",
    # System / IDE
    ".DS_Store",
    "Thumbs.db",
    # Binary / Data artifacts
    ".coverage",  # <--- Likely binary culprit
    "db.sqlite3",
    "dump.rdb",
}

DEFAULT_IGNORE_DIRS = {
    # Dependencies
    "node_modules",
    ".venv",
    "venv",
    "env",
    "target",  # Rust
    "vendor",  # Go / PHP
    # Build Artifacts
    "dist",
    "build",
    "out",
    ".next",
    ".turbo",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "htmlcov",
    ".cache",
    # VCS / IDE
    ".git",
    ".github",  # Optional: keep if you want CI workflows
    ".idea",
    ".vscode",
    # Project-specific exclusions
    ".jnkn",
    "scripts",
    "tests",
    "site",
    "docs",
}

DEFAULT_IGNORE_EXTENSIONS = {
    # Images / Media
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".svg",
    ".webp",
    ".mp4",
    ".mov",
    ".avi",
    ".webm",
    ".mp3",
    ".wav",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".rar",
    # Fonts
    ".ttf",
    ".otf",
    ".woff",
    ".woff2",
    ".eot",
    # Compiled / Binary
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
    ".bin",
    ".dll",
    ".so",
    ".dylib",
    ".class",
    ".jar",
    ".pkl",
    ".parquet",
    ".onnx",
    ".pt",
    ".pth",  # ML Models
    ".db",
    ".sqlite",
    ".sqlite3",
}

# ------------------------------------------------------------
# HELPERS
# ------------------------------------------------------------


def is_binary(file_path: Path) -> bool:
    """
    Heuristic binary detection.
    Reads the first 1024 bytes and looks for NULL bytes.
    """
    try:
        with file_path.open("rb") as f:
            return b"\0" in f.read(1024)
    except Exception:
        # If we can't read it safely, treat as binary
        return True


def is_under_master_paths(file_path: Path, root: Path) -> bool:
    """
    Returns True if file_path is under any MASTER_INCLUDE_PATHS.
    If MASTER_INCLUDE_PATHS is empty, always returns True.
    """
    if not MASTER_INCLUDE_PATHS:
        return True

    rel_path = file_path.relative_to(root)

    for include in MASTER_INCLUDE_PATHS:
        try:
            rel_path.relative_to(Path(include))
            return True
        except ValueError:
            continue

    return False


# ------------------------------------------------------------
# MAIN LOGIC
# ------------------------------------------------------------


def concat_all(output_file: str = "all_repos.txt") -> None:
    """Recursively scans and concatenates text files."""

    root = Path(".").resolve()
    output_lines: list[str] = []

    ignore_files = DEFAULT_IGNORE_FILES
    ignore_dirs = DEFAULT_IGNORE_DIRS
    ignore_exts = DEFAULT_IGNORE_EXTENSIONS

    print(f"🔎 Scanning root: {root}")
    if MASTER_INCLUDE_PATHS:
        print(f"🎯 Master include paths: {MASTER_INCLUDE_PATHS}")
    else:
        print("🌍 No master include filter (scanning full repo)")

    print(
        f"🚫 Ignoring binaries, lockfiles, and files > {MAX_FILE_SIZE_BYTES / 1024:.0f} KB"
    )

    for dirpath, dirnames, filenames in os.walk(root):
        # 1. Prune ignored directories in-place
        dirnames[:] = [
            d for d in dirnames if d not in ignore_dirs and not d.startswith(".")
        ]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            rel_path = file_path.relative_to(root)

            # 0. Master include filter (short-circuit)
            if not is_under_master_paths(file_path, root):
                continue

            # 2. Skip ignored filenames
            if filename in ignore_files:
                continue

            # 3. Skip ignored extensions
            if file_path.suffix.lower() in ignore_exts:
                continue

            # 4. Skip files inside ignored directories (defensive check)
            if any(part in ignore_dirs for part in file_path.parts):
                continue

            # 5. Skip large files
            try:
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE_BYTES:
                    print(f"⚠️  Skipping large file: {rel_path} ({size / 1024:.1f} KB)")
                    continue
            except Exception:
                continue

            # 6. Binary detection
            if is_binary(file_path):
                print(f"⚠️  Skipping binary file: {rel_path}")
                continue

            # 7. Read and append
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")

                # Skip empty files
                if not text.strip():
                    continue

                output_lines.append("\n" + "=" * 40 + "\n")
                output_lines.append(f" FILE: {rel_path}\n")
                output_lines.append("=" * 40 + "\n")
                output_lines.append(text)
                output_lines.append("\n")

            except Exception as e:
                print(f"❌ Error reading {rel_path}: {e}")

    out_path = root / output_file
    out_path.write_text("".join(output_lines), encoding="utf-8")

    print(f"\n✅ Done! Included {len(output_lines) // 5} files.")
    print(f"📄 Output written to: {out_path}")


# ------------------------------------------------------------
# ENTRYPOINT
# ------------------------------------------------------------

if __name__ == "__main__":
    concat_all()
