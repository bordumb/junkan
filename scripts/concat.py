#!/usr/bin/env python3
import os
from pathlib import Path

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
    ".coverage",  # <--- This was your likely binary culprit
    "db.sqlite3",
    "dump.rdb",
}

DEFAULT_IGNORE_DIRS = {
    # Dependencies
    "node_modules",
    ".venv",
    "venv",
    "env",
    "target", # Rust
    "vendor", # Go/PHP

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

    # VCS
    ".git",
    ".github", # Optional: keep if you want CI workflows
    ".idea",
    ".vscode",

    # Tests
    "scripts",
    "tests/unit"
    "site",
    
}

DEFAULT_IGNORE_EXTENSIONS = {
    # Images/Media
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp",
    ".mp4", ".mov", ".avi", ".webm", ".mp3", ".wav",
    ".pdf", ".zip", ".tar", ".gz", ".7z", ".rar",

    # Fonts
    ".ttf", ".otf", ".woff", ".woff2", ".eot",

    # Compiled/Binary
    ".pyc", ".pyo", ".pyd",
    ".exe", ".bin", ".dll", ".so", ".dylib", ".class", ".jar",
    ".pkl", ".parquet", ".onnx", ".pt", ".pth", # ML Models
    ".db", ".sqlite", ".sqlite3",
}

# ------------------------------------------------------------
# LOGIC
# ------------------------------------------------------------

def is_binary(file_path: Path) -> bool:
    """
    Heuristic to check if a file is binary.
    Reads the first 1024 bytes and looks for null bytes.
    """
    try:
        with file_path.open("rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except Exception:
        return True  # If we can't read it, skip it

def concat_all(output_file="all_repos.txt"):
    """Recursively scans and concatenates text files."""

    root = Path(".").resolve()
    output_lines = []

    # Sets for fast O(1) lookups
    ignore_files = DEFAULT_IGNORE_FILES
    ignore_dirs = DEFAULT_IGNORE_DIRS
    ignore_exts = DEFAULT_IGNORE_EXTENSIONS

    print(f"🔎 Scanning: {root}")
    print(f"🚫 Ignoring: binaries, lockfiles, >{MAX_FILE_SIZE_BYTES/1024:.0f}KB")

    # Use os.walk for better control over directory pruning
    for dirpath, dirnames, filenames in os.walk(root):

        # 1. Prune ignored directories in-place
        # We must modify 'dirnames' list to stop os.walk from entering them
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs and not d.startswith(".")]

        for filename in filenames:
            file_path = Path(dirpath) / filename
            rel_path = file_path.relative_to(root)

            # 2. Skip ignored filenames
            if filename in ignore_files:
                continue

            # 3. Skip ignored extensions
            if file_path.suffix.lower() in ignore_exts:
                continue

            # 4. Skip files strictly inside ignored folders (double check for path parts)
            # This handles cases like `apps/web/.next` which might slip through top-level pruning
            if any(part in ignore_dirs for part in file_path.parts):
                continue

            # 5. Skip large files
            try:
                size = file_path.stat().st_size
                if size > MAX_FILE_SIZE_BYTES:
                    print(f"⚠️  Skipping large file: {rel_path} ({size/1024:.1f} KB)")
                    continue
            except Exception:
                continue

            # 6. Binary Detection (Crucial Step)
            if is_binary(file_path):
                print(f"⚠️  Skipping binary file: {rel_path}")
                continue

            # 7. Read and Append
            try:
                text = file_path.read_text(encoding="utf-8", errors="ignore")

                # Optional: Skip empty files
                if not text.strip():
                    continue

                output_lines.append(f"\n{'='*40}\n")
                output_lines.append(f" FILE: {rel_path}\n")
                output_lines.append(f"{'='*40}\n")
                output_lines.append(text)
                output_lines.append("\n")

            except Exception as e:
                print(f"❌ Error reading {rel_path}: {e}")

    # Write output
    out_path = root / output_file
    out_path.write_text("".join(output_lines), encoding="utf-8")

    print(f"\n✅ Done! Scanned {len(output_lines)//5} files.")
    print(f"📄 Output written to: {out_path}")

if __name__ == "__main__":
    concat_all()
