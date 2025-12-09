# Column-Level Lineage Design

## Problem Statement

Current parser extracts table-level lineage:
- `process_events.py` READS `warehouse.dim_users`
- `process_events.py` WRITES `warehouse.fact_events`

But engineers need column-level lineage:
- `warehouse.fact_events.user_segment` comes from `warehouse.dim_users.segment`
- `warehouse.fact_events.total_revenue` is computed from `staging.events.revenue`

## Extraction Patterns

### Pattern 1: SQL Strings (Easiest)
```python
spark.sql("SELECT column_a, column_b FROM database.table WHERE column_a = 'xyz'")
spark.sql("""
    SELECT 
        t1.user_id,
        t1.event_count,
        t2.segment
    FROM warehouse.events t1
    JOIN warehouse.users t2 ON t1.user_id = t2.user_id
""")
```

**Approach:** Use sqlglot to parse SQL and extract:
- SELECT columns → output columns
- FROM/JOIN tables → source tables
- WHERE/ON columns → filter columns
- Column aliases → transformations

### Pattern 2: DataFrame Method Chains (Medium)
```python
read_df = spark.read.parquet("hdfs://path/to/table")
filtered_df = read_df.filter(col("column_a") == 'xyz')
selected_df = filtered_df.select("column_a", "column_b")
result = selected_df.withColumn("new_col", col("column_a") + col("column_b"))
```

**Approach:** Track DataFrame transformations:
- `.select()` → output columns
- `.filter()` / `.where()` → filter columns
- `.withColumn()` → new column + source columns
- `.groupBy()` → grouping columns
- `.agg()` → aggregation columns
- `.join()` → join keys + source columns

### Pattern 3: Dynamic/Variable References (Hard)
```python
grouping_fields = ["column_a", "column_b"]
filter_value = 'xyz'

filtered_df = read_df.filter(col("column_a") == filter_value)
selected_df = filtered_df.select(grouping_fields)
selected_df = filtered_df.select(*grouping_fields)
```

**Approach:** 
- Track variable assignments (AST analysis)
- Resolve list literals to column names
- Handle `*args` unpacking
- Mark as "dynamic" when truly unresolvable

### Pattern 4: F-expressions and col() (Medium)
```python
from pyspark.sql import functions as F
from pyspark.sql.functions import col, sum, avg

df.select(F.col("a"), F.sum("b").alias("total_b"))
df.withColumn("ratio", F.col("a") / F.col("b"))
df.filter(F.col("status") == "active")
```

**Approach:** Extract column names from:
- `col("name")`, `F.col("name")`
- `F.sum("name")`, `F.avg("name")`, etc.
- `df["column"]` bracket notation
- `.alias("new_name")` for output naming

## Data Model

```python
@dataclass
class ColumnReference:
    """A reference to a column in the code."""
    column_name: str
    table_name: Optional[str]  # If known
    line_number: int
    context: str  # "select", "filter", "groupby", "join", "agg", "write"
    is_dynamic: bool = False  # True if from variable
    alias: Optional[str] = None  # If renamed

@dataclass
class ColumnLineage:
    """Lineage for a single output column."""
    output_column: str
    output_table: str
    source_columns: List[ColumnReference]
    transformation: Optional[str]  # "direct", "sum", "concat", "case", etc.

@dataclass 
class FileColumnLineage:
    """All column lineage extracted from a file."""
    file_path: str
    columns_read: List[ColumnReference]
    columns_written: List[ColumnReference]
    lineage: List[ColumnLineage]  # Output → Source mappings
```

## Implementation Strategy

### Phase 1: SQL String Extraction (This PR)
- Parse SQL strings with sqlglot
- Extract SELECT columns, FROM tables, WHERE columns
- Handle JOINs and subqueries
- High accuracy, well-defined grammar

### Phase 2: DataFrame Method Tracking (Next PR)
- Regex-based extraction of .select(), .filter(), etc.
- Extract column names from method arguments
- Track method chains to infer flow

### Phase 3: Variable Resolution (Future)
- AST-based analysis for variable tracking
- Resolve list literals and f-strings
- Mark unresolvable as "dynamic"

## Confidence Levels

| Pattern | Confidence | Example |
|---------|------------|---------|
| SQL string literal | HIGH | `spark.sql("SELECT a FROM t")` |
| Direct column ref | HIGH | `.select("col_a", "col_b")` |
| col() function | HIGH | `.filter(col("status") == "x")` |
| List variable (literal) | MEDIUM | `cols = ["a", "b"]; df.select(cols)` |
| Config/param variable | LOW | `df.select(config.columns)` |
| Dynamic expression | UNKNOWN | `df.select(*get_columns())` |

## Output Format

```json
{
  "file": "jobs/process_events.py",
  "table_lineage": {
    "reads": ["staging.events", "warehouse.users"],
    "writes": ["warehouse.fact_events"]
  },
  "column_lineage": [
    {
      "output": "warehouse.fact_events.user_segment",
      "sources": [
        {"table": "warehouse.users", "column": "segment", "transform": "direct"}
      ],
      "confidence": "high"
    },
    {
      "output": "warehouse.fact_events.total_revenue",
      "sources": [
        {"table": "staging.events", "column": "revenue", "transform": "sum"}
      ],
      "confidence": "high"
    },
    {
      "output": "warehouse.fact_events.event_date",
      "sources": [
        {"table": "staging.events", "column": "event_timestamp", "transform": "to_date"}
      ],
      "confidence": "high"
    }
  ],
  "dynamic_columns": [
    {
      "location": "line 45",
      "pattern": "df.select(*grouping_fields)",
      "note": "columns from variable 'grouping_fields'"
    }
  ]
}
```

## Test Cases

### SQL Extraction
```python
# Simple SELECT
spark.sql("SELECT user_id, name FROM users")
# → reads: users.user_id, users.name

# JOIN
spark.sql("""
    SELECT a.id, b.value 
    FROM table_a a 
    JOIN table_b b ON a.id = b.id
""")
# → reads: table_a.id, table_b.value, table_b.id

# Aggregation
spark.sql("SELECT category, SUM(amount) as total FROM sales GROUP BY category")
# → reads: sales.category, sales.amount
# → output: total (from SUM(amount))
```

### DataFrame Method Extraction
```python
# Select
df.select("a", "b", "c")
# → columns: a, b, c

# Filter
df.filter(col("status") == "active")
# → filter column: status

# WithColumn
df.withColumn("full_name", concat(col("first"), col("last")))
# → output: full_name
# → sources: first, last
# → transform: concat

# GroupBy + Agg
df.groupBy("category").agg(sum("amount").alias("total"))
# → grouping: category
# → aggregation: amount → total (sum)
```

### Variable Resolution
```python
# Resolvable
cols = ["a", "b", "c"]
df.select(cols)
# → columns: a, b, c (confidence: medium)

# Partially resolvable
base_cols = ["id", "name"]
df.select(*base_cols, "extra_col")
# → columns: id, name, extra_col

# Not resolvable
df.select(get_dynamic_columns())
# → columns: UNKNOWN (flag for review)
```