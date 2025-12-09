#!/usr/bin/env python3
"""
Test cases for column-level lineage extraction.

Covers:
1. SQL strings in spark.sql()
2. DataFrame method chains
3. Variable-based column references
4. Dynamic/unresolvable patterns
"""

import json
from jnkn.parsing.pyspark.column_lineage import extract_column_lineage, ColumnLineageExtractor


def test_sql_extraction():
    """Test extraction from spark.sql() calls."""
    
    code = '''
from pyspark.sql import SparkSession
spark = SparkSession.builder.getOrCreate()

# Simple SELECT
df1 = spark.sql("SELECT column_a, column_b FROM database.table WHERE column_a = 'xyz'")

# SELECT with table alias
df2 = spark.sql("""
    SELECT 
        t.user_id,
        t.event_type,
        SUM(t.amount) as total_amount
    FROM warehouse.events t
    WHERE t.status = 'active'
    GROUP BY t.user_id, t.event_type
""")

# JOIN query
df3 = spark.sql("""
    SELECT 
        a.id,
        a.name,
        b.value,
        b.category
    FROM schema.table_a a
    JOIN schema.table_b b ON a.id = b.foreign_id
    WHERE a.active = true
""")
'''
    
    result = extract_column_lineage(code, "test_sql.py")
    
    print("=" * 60)
    print("TEST: SQL String Extraction")
    print("=" * 60)
    print(f"Columns read: {len(result.columns_read)}")
    
    # Check specific columns were extracted
    col_names = {c.column for c in result.columns_read}
    expected = {"column_a", "column_b", "user_id", "event_type", "amount", "status", 
                "id", "name", "value", "category", "foreign_id", "active"}
    
    found = expected & col_names
    missing = expected - col_names
    
    print(f"Expected columns found: {len(found)}/{len(expected)}")
    if missing:
        print(f"Missing: {missing}")
    
    # Check contexts
    select_cols = [c for c in result.columns_read if c.context.value == "select"]
    filter_cols = [c for c in result.columns_read if c.context.value == "filter"]
    groupby_cols = [c for c in result.columns_read if c.context.value == "groupby"]
    join_cols = [c for c in result.columns_read if c.context.value == "join"]
    
    print(f"SELECT columns: {len(select_cols)}")
    print(f"FILTER columns: {len(filter_cols)}")
    print(f"GROUP BY columns: {len(groupby_cols)}")
    print(f"JOIN columns: {len(join_cols)}")
    print()
    
    return result


def test_dataframe_methods():
    """Test extraction from DataFrame method chains."""
    
    code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

# Read and filter
read_df = spark.read.parquet("hdfs://group/data_eng/database/table/date={date_partition}/file.parquet")
filtered_df = read_df.filter(col("column_a") == 'xyz')
selected_df = filtered_df.select("column_a", "column_b")

# Method chain
result_df = spark.read.parquet("s3://bucket/data/") \\
    .filter(col("status") == "active") \\
    .select("user_id", "event_type", "amount") \\
    .withColumn("amount_cents", col("amount") * 100)

# GroupBy with aggregation
summary = result_df \\
    .groupBy("user_id", "event_type") \\
    .agg(
        sum("amount").alias("total_amount"),
        avg("quantity").alias("avg_quantity"),
        count("event_id").alias("event_count")
    )

# Join
joined = result_df.join(
    other_df,
    ["user_id", "date"],
    "left"
)

# Order by
sorted_df = summary.orderBy("total_amount", col("user_id").desc())
'''
    
    result = extract_column_lineage(code, "test_df.py")
    
    print("=" * 60)
    print("TEST: DataFrame Method Extraction")
    print("=" * 60)
    print(f"Columns read: {len(result.columns_read)}")
    print(f"Columns written: {len(result.columns_written)}")
    
    col_names = {c.column for c in result.columns_read}
    expected = {"column_a", "column_b", "status", "user_id", "event_type", 
                "amount", "quantity", "event_id", "date", "total_amount"}
    
    found = expected & col_names
    print(f"Expected columns found: {len(found)}/{len(expected)}")
    
    # Check written columns
    written_names = {c.column for c in result.columns_written}
    expected_written = {"amount_cents", "total_amount", "avg_quantity", "event_count"}
    found_written = expected_written & written_names
    print(f"Written columns found: {len(found_written)}/{len(expected_written)}")
    
    print()
    return result


def test_variable_resolution():
    """Test extraction with variable-based column references."""
    
    code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

# Resolvable list variable
grouping_fields = ["column_a", "column_b"]
filter_value = 'xyz'

read_df = spark.read.parquet("hdfs://path/to/data/")
filtered_df = read_df.filter(col("column_a") == filter_value)
selected_df = filtered_df.select(grouping_fields)

# Star unpacking
base_cols = ["id", "name", "date"]
extra_col = "status"
full_df = read_df.select(*base_cols, extra_col, "amount")

# GroupBy with variable
agg_columns = ["revenue", "count"]
grouped = read_df.groupBy(grouping_fields).sum("amount")

# Partial resolution - some static, some dynamic
mixed_df = read_df.select("static_col", *base_cols)
'''
    
    result = extract_column_lineage(code, "test_vars.py")
    
    print("=" * 60)
    print("TEST: Variable Resolution")
    print("=" * 60)
    print(f"Columns read: {len(result.columns_read)}")
    print(f"Dynamic refs: {len(result.dynamic_refs)}")
    
    # Check resolved variables
    col_names = {c.column for c in result.columns_read}
    expected_resolved = {"column_a", "column_b", "id", "name", "date", "status", "amount", "static_col"}
    
    found = expected_resolved & col_names
    print(f"Resolved columns: {len(found)}/{len(expected_resolved)}")
    
    # Check confidence levels
    high_conf = [c for c in result.columns_read if c.confidence.label == "high"]
    medium_conf = [c for c in result.columns_read if c.confidence.label == "medium"]
    
    print(f"High confidence: {len(high_conf)}")
    print(f"Medium confidence (from variables): {len(medium_conf)}")
    
    print()
    return result


def test_dynamic_patterns():
    """Test detection of unresolvable dynamic patterns."""
    
    code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()
df = spark.read.parquet("s3://data/")

# Function call - unresolvable
dynamic_cols = get_columns_from_config()
df1 = df.select(dynamic_cols)

# Config object - unresolvable
df2 = df.select(config.column_list)

# Parameter - unresolvable
def process_data(columns):
    return df.select(columns)

# Method result - unresolvable
df3 = df.select(schema.get_output_columns())

# Conditional - partially resolvable
use_all = True
if use_all:
    cols = ["a", "b", "c"]
else:
    cols = ["a"]
df4 = df.select(cols)  # cols is resolved in this scope
'''
    
    result = extract_column_lineage(code, "test_dynamic.py")
    
    print("=" * 60)
    print("TEST: Dynamic/Unresolvable Patterns")
    print("=" * 60)
    print(f"Columns read: {len(result.columns_read)}")
    print(f"Dynamic refs: {len(result.dynamic_refs)}")
    
    for dyn in result.dynamic_refs:
        print(f"  - Line {dyn.line_number}: {dyn.note}")
    
    print()
    return result


def test_complex_transforms():
    """Test extraction of complex transformations."""
    
    code = '''
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col, concat, when, lit, to_date

spark = SparkSession.builder.getOrCreate()
df = spark.read.parquet("s3://data/")

# Concat transformation
df = df.withColumn("full_name", concat(col("first_name"), lit(" "), col("last_name")))

# Date transformation
df = df.withColumn("event_date", to_date(col("event_timestamp"), "yyyy-MM-dd"))

# Conditional transformation
df = df.withColumn("status_label", 
    when(col("status") == 1, "active")
    .when(col("status") == 2, "pending")
    .otherwise("inactive")
)

# Arithmetic transformation
df = df.withColumn("total_with_tax", col("amount") * 1.1)

# Nested function
df = df.withColumn("clean_email", 
    F.lower(F.trim(col("email")))
)

# Multiple source columns
df = df.withColumn("full_address",
    concat(
        col("street"), lit(", "),
        col("city"), lit(", "),
        col("state"), lit(" "),
        col("zip")
    )
)
'''
    
    result = extract_column_lineage(code, "test_transforms.py")
    
    print("=" * 60)
    print("TEST: Complex Transformations")
    print("=" * 60)
    print(f"Columns read: {len(result.columns_read)}")
    print(f"Columns written: {len(result.columns_written)}")
    print(f"Lineage mappings: {len(result.lineage)}")
    
    # Show lineage
    print("\nLineage mappings:")
    for mapping in result.lineage:
        sources = [s.column for s in mapping.source_columns]
        print(f"  {mapping.output_column} <- {sources}")
    
    print()
    return result


def test_your_examples():
    """Test the specific examples from your message."""
    
    code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

# Example 1: SparkSQL
df1 = spark.sql("SELECT column_a, column_b FROM database.table WHERE column_a = 'xyz'")

# Example 2: DataFrame methods
read_df = spark.read.parquet("hdfs://group/data_eng/database/table/.../date={date_partition}/file_name.parquet")
filtered_df = read_df.filter(col("column_a") == 'xyz')
selected_df = filtered_df.select("column_a", "column_b")

# Example 3: Dynamic with variables
grouping_fields = ["column_a", "column_b"]
filter_value = 'xyz'

read_df2 = spark.read.parquet("hdfs://group/data_eng/database/table/.../date={date_partition}/file_name.parquet")
filtered_df2 = read_df2.filter(col("column_a") == filter_value)
selected_df2 = filtered_df2.select(grouping_fields)
'''
    
    result = extract_column_lineage(code, "your_examples.py")
    
    print("=" * 60)
    print("TEST: Your Specific Examples")
    print("=" * 60)
    
    print(f"Total columns read: {len(result.columns_read)}")
    print(f"Dynamic refs: {len(result.dynamic_refs)}")
    
    print("\nColumns found:")
    for col_ref in result.columns_read:
        conf = col_ref.confidence.label
        ctx = col_ref.context.value
        print(f"  {col_ref.column:20} [{ctx:8}] (confidence: {conf})")
    
    print()
    return result


def main():
    print("\n" + "=" * 60)
    print("COLUMN LINEAGE EXTRACTION TEST SUITE")
    print("=" * 60 + "\n")
    
    test_sql_extraction()
    test_dataframe_methods()
    test_variable_resolution()
    test_dynamic_patterns()
    test_complex_transforms()
    test_your_examples()
    
    print("=" * 60)
    print("ALL TESTS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()