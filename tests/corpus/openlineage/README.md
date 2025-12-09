Here is the `README.md` file for your OpenLineage test corpus, including the directory structure and the exact command to run the validation.

**File Path:** `tests/corpus/openlineage/README.md`

```markdown
# OpenLineage Test Corpus

This directory contains ground-truth test cases for the OpenLineage parser (`src/junkan/parsing/openlineage`). It is used to verify that runtime lineage events are correctly parsed into Junkan's graph structure.

## Directory Structure

```

openlineage/
├── basic\_run/             \# ✅ Basic Job -\> Input/Output lineage
│   ├── input.json         \# Standard OpenLineage COMPLETE event
│   └── expected.json      \# Expected Job and Table nodes
│
└── column\_level/          \# ✅ Column-level lineage facets
├── input.json         \# Event with schema and columnLineage facets
└── expected.json      \# Expected Column nodes and transformations

````

## Test Case Descriptions

### 1. Basic Run (`basic_run`)
Tests the parsing of a standard `COMPLETE` event.
- **Input:** A Spark job reading from Postgres and writing to S3.
- **Validation:** Ensures `NodeType.JOB` and `NodeType.DATA_ASSET` nodes are created, along with `READS` and `WRITES` edges.

### 2. Column Level (`column_level`)
Tests the extraction of fine-grained lineage from event facets.
- **Input:** An event containing `schema` and `columnLineage` facets.
- **Validation:** Ensures `NodeType.DATA_ASSET` nodes are created for specific columns (e.g., `column:db/users/id`) and linked via `TRANSFORMS` edges.

## Parsing Logic

The OpenLineage parser maps events to Junkan nodes as follows:
```
| OpenLineage Concept | Junkan Node Type | ID Format |
|---------------------|------------------|-----------|
| Job | `JOB` | `job:{namespace}/{name}` |
| Input Dataset | `DATA_ASSET` | `data:{namespace}/{name}` |
| Output Dataset | `DATA_ASSET` | `data:{namespace}/{name}` |
| Schema Field | `DATA_ASSET` | `column:{namespace}/{dataset}/{field}` |
```

## How to Run the Tests

To score the OpenLineage parser against this corpus, run the following command from the repository root:

```bash
uv run python -m tests.utils.score_corpus --parser openlineage --verbose
````

### Expected Output

A successful run should show 100% recall with no missed nodes:

```text
OPENLINEAGE PARSER
  Cases:     2/2 passed
  Precision: 100.0%
  Recall:    100.0%
  F1 Score:  1.00

✅ PRODUCTION READY: Average recall 100.0%
```
