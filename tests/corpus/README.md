# Junkan Test Corpus

Ground-truth test cases for measuring parser accuracy.

## Structure

```
corpus/
├── python/                     # Python parser test cases
│   ├── basic_os_getenv/       # ✅ Basic patterns (should pass)
│   ├── from_import_patterns/  # ✅ After from-imports (should pass)
│   ├── class_level_env/       # ⚠️ Class/module scope (may partially pass)
│   └── pydantic_settings/     # ❌ Pydantic BaseSettings (likely fails)
│
├── terraform/                  # Terraform parser test cases
│   ├── basic_resources/       # ✅ Basic resources (should pass)
│   └── module_composition/    # ❌ Module support (likely fails)
│
└── integration/               # Cross-domain stitching tests
    └── env_to_rds/           # Python env vars → Terraform resources
```

## Running the Scorer

```bash
# Score all parsers
uv run python -m tests.utils.score_corpus

# Score specific parser
uv run python -m tests.utils.score_corpus --parser python

# Verbose output
uv run python -m tests.utils.score_corpus --verbose

# Save detailed report
uv run python -m tests.utils.score_corpus --report scores.json
```

## Test Case Format

Each test case directory contains:
- `input.py` / `input.tf` - Source file to parse
- `expected.json` - Ground truth detections

## Adding New Test Cases

1. Create directory: `mkdir -p tests/corpus/python/my_pattern`
2. Add input file: `tests/corpus/python/my_pattern/input.py`
3. Add expected: `tests/corpus/python/my_pattern/expected.json`
4. Run: `uv run python -m tests.utils.score_corpus --case my_pattern -v`
