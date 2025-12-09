#!/usr/bin/env python3
"""
End-to-End Demo: Diff-Aware Analysis

This demo shows how jnkn's diff analyzer works:
1. Compare two versions of PySpark code
2. Detect semantic changes (not just text diff)
3. Identify breaking changes
4. Generate reports for CI/CD

The key insight:
    "File X was modified" → Not actionable
    "Column 'user_id' was removed from SELECT" → Actionable!
"""

import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from jnkn.analysis.diff_analyzer import diff_code, DiffReport, ChangeType


# =============================================================================
# Demo Scenarios
# =============================================================================

def scenario_1_column_removed():
    """
    Scenario 1: A column is removed from the output.
    
    This is a BREAKING CHANGE because downstream consumers
    may depend on this column.
    """
    print("=" * 70)
    print("SCENARIO 1: Column Removed (BREAKING)")
    print("=" * 70)
    
    base_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.events")

result = df.select(
    "user_id",
    "event_type", 
    "amount",
    "created_at",    # This column will be removed
    "status"
)

result.write.saveAsTable("warehouse.processed_events")
'''

    head_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.events")

result = df.select(
    "user_id",
    "event_type", 
    "amount",
    # created_at removed!
    "status"
)

result.write.saveAsTable("warehouse.processed_events")
'''

    report = diff_code(base_code, head_code, "events_processor.py")
    _print_scenario_report(report)
    
    print("\n💡 Impact: Any downstream job selecting 'created_at' will fail!")
    print("   jnkn would flag this as a BREAKING CHANGE.")
    
    return report


def scenario_2_column_added():
    """
    Scenario 2: A new column is added.
    
    This is generally SAFE - backward compatible.
    """
    print("\n" + "=" * 70)
    print("SCENARIO 2: Column Added (SAFE)")
    print("=" * 70)
    
    base_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.orders")

summary = df.groupBy("customer_id").agg(
    sum("amount").alias("total_amount")
)

summary.write.saveAsTable("warehouse.customer_summary")
'''

    head_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, avg, count

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.orders")

summary = df.groupBy("customer_id").agg(
    sum("amount").alias("total_amount"),
    avg("amount").alias("avg_amount"),      # NEW
    count("order_id").alias("order_count")  # NEW
)

summary.write.saveAsTable("warehouse.customer_summary")
'''

    report = diff_code(base_code, head_code, "customer_summary.py")
    _print_scenario_report(report)
    
    print("\n💡 Impact: Safe change - new columns don't break existing consumers.")
    print("   Downstream jobs can optionally start using the new columns.")
    
    return report


def scenario_3_transform_changed():
    """
    Scenario 3: A transformation logic is changed.
    
    This may be BREAKING if downstream expects specific values.
    """
    print("\n" + "=" * 70)
    print("SCENARIO 3: Transform Logic Changed (POTENTIALLY BREAKING)")
    print("=" * 70)
    
    base_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.transactions")

# Calculate revenue as simple sum
result = df.groupBy("product_id").agg(
    sum("price").alias("revenue")  # Simple sum
)

result.write.saveAsTable("warehouse.product_revenue")
'''

    head_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, when

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.transactions")

# Calculate revenue excluding refunds
result = df.filter(col("status") != "refunded").groupBy("product_id").agg(
    sum("price").alias("revenue")  # Now excludes refunds!
)

result.write.saveAsTable("warehouse.product_revenue")
'''

    report = diff_code(base_code, head_code, "product_revenue.py")
    _print_scenario_report(report)
    
    print("\n💡 Impact: The 'revenue' column now has different semantics!")
    print("   Downstream dashboards may show different numbers.")
    print("   This is a data quality risk, not a schema break.")
    
    return report


def scenario_4_filter_changed():
    """
    Scenario 4: Filter criteria changed.
    
    This changes the data volume and composition.
    """
    print("\n" + "=" * 70)
    print("SCENARIO 4: Filter Criteria Changed (DATA CHANGE)")
    print("=" * 70)
    
    base_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.users")

# Filter: only active users
active_users = df.filter(col("status") == "active")

active_users.select(
    "user_id", 
    "email",
    "region"
).write.saveAsTable("warehouse.active_users")
'''

    head_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col

spark = SparkSession.builder.getOrCreate()

df = spark.read.table("warehouse.users")

# Filter: active users in US only (more restrictive!)
active_users = df.filter(col("status") == "active").filter(col("region") == "US")

active_users.select(
    "user_id", 
    "email",
    "region"
).write.saveAsTable("warehouse.active_users")
'''

    report = diff_code(base_code, head_code, "active_users.py")
    _print_scenario_report(report)
    
    print("\n💡 Impact: Output now only includes US users!")
    print("   Row count will drop significantly.")
    print("   Downstream jobs expecting global users will have missing data.")
    
    return report


def scenario_5_table_source_changed():
    """
    Scenario 5: Source table changed.
    
    This is a significant change in data lineage.
    """
    print("\n" + "=" * 70)
    print("SCENARIO 5: Source Table Changed (LINEAGE BREAK)")
    print("=" * 70)
    
    base_code = '''
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Read from production database
df = spark.read.table("prod_db.orders")

result = df.select("order_id", "customer_id", "amount")
result.write.saveAsTable("warehouse.orders_snapshot")
'''

    head_code = '''
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# Read from staging database instead!
df = spark.read.table("staging_db.orders")

result = df.select("order_id", "customer_id", "amount")
result.write.saveAsTable("warehouse.orders_snapshot")
'''

    report = diff_code(base_code, head_code, "orders_snapshot.py")
    _print_scenario_report(report)
    
    print("\n💡 Impact: Data source completely changed!")
    print("   Production → Staging means test data in prod tables.")
    print("   This should definitely be caught in code review.")
    
    return report


def scenario_6_multiple_changes():
    """
    Scenario 6: Multiple changes in one PR.
    
    Real-world PRs often have multiple changes.
    """
    print("\n" + "=" * 70)
    print("SCENARIO 6: Multiple Changes (REAL-WORLD PR)")
    print("=" * 70)
    
    base_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, concat, lit

spark = SparkSession.builder.getOrCreate()

# Read source
events = spark.read.table("warehouse.raw_events")
users = spark.read.table("warehouse.dim_users")

# Join and process
joined = events.join(users, "user_id", "left")

result = joined.filter(col("event_type") == "purchase") \\
    .select(
        "user_id",
        "event_id",
        "amount",
        "old_metric",  # Will be removed
        concat(col("first_name"), lit(" "), col("last_name")).alias("full_name")
    ) \\
    .groupBy("user_id", "full_name") \\
    .agg(sum("amount").alias("total_purchases"))

result.write.saveAsTable("warehouse.user_purchases")
'''

    head_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, avg, concat, lit, when

spark = SparkSession.builder.getOrCreate()

# Read source (added new table)
events = spark.read.table("warehouse.raw_events")
users = spark.read.table("warehouse.dim_users")
regions = spark.read.table("warehouse.dim_regions")  # NEW SOURCE

# Join and process (added region join)
joined = events.join(users, "user_id", "left") \\
    .join(regions, "region_id", "left")  # NEW JOIN

result = joined.filter(col("event_type") == "purchase") \\
    .filter(col("is_valid") == True) \\  # NEW FILTER
    .select(
        "user_id",
        "event_id",
        "amount",
        "region_name",  # NEW COLUMN (replaces old_metric)
        concat(col("first_name"), lit(" "), col("last_name")).alias("full_name")
    ) \\
    .groupBy("user_id", "full_name", "region_name") \\  # MODIFIED GROUPBY
    .agg(
        sum("amount").alias("total_purchases"),
        avg("amount").alias("avg_purchase")  # NEW AGG
    )

result.write.saveAsTable("warehouse.user_purchases")
'''

    report = diff_code(base_code, head_code, "user_purchases.py")
    _print_scenario_report(report)
    
    print("\n💡 This PR has multiple changes:")
    print("   - BREAKING: 'old_metric' column removed")
    print("   - SAFE: 'region_name' column added")
    print("   - SAFE: 'avg_purchase' aggregation added")
    print("   - DATA CHANGE: New filter on 'is_valid'")
    print("   - LINEAGE: New source table 'dim_regions'")
    
    return report


def _print_scenario_report(report: DiffReport):
    """Print a formatted scenario report."""
    print()
    
    # Summary
    s = report.summary
    print("📊 Analysis Results:")
    print(f"   Columns Added:      {s['columns_added']}")
    print(f"   Columns Removed:    {s['columns_removed']}")
    print(f"   Lineage Changed:    {s['lineage_mappings_changed']}")
    print(f"   Transforms Changed: {s['transforms_changed']}")
    
    # Breaking changes
    if report.has_breaking_changes:
        print()
        print("\033[91m⚠️  BREAKING CHANGES:\033[0m")
        for c in report.column_changes:
            if c.change_type == ChangeType.REMOVED:
                print(f"   🗑️  Column removed: {c.column} ({c.context})")
    
    # Column changes
    if report.column_changes:
        print()
        print("Column Changes:")
        for c in report.column_changes:
            icon = {"added": "➕", "removed": "🗑️", "modified": "✏️"}.get(c.change_type.value, "?")
            print(f"   {icon} {c.change_type.value.upper()}: {c.column} ({c.context})")
    
    # Lineage changes
    if report.lineage_changes:
        print()
        print("Lineage Changes:")
        for lc in report.lineage_changes:
            print(f"   {lc}")
    
    # Transform changes
    if report.transform_changes:
        print()
        print("Transform Changes:")
        for tc in report.transform_changes:
            print(f"   {tc}")


# =============================================================================
# Integration Examples
# =============================================================================

def show_cli_usage():
    """Show CLI usage examples."""
    print("\n" + "=" * 70)
    print("CLI USAGE")
    print("=" * 70)
    
    print("""
    # Basic diff against main
    jnkn diff main HEAD
    
    # Compare specific branches
    jnkn diff feature-branch origin/main
    
    # Output as JSON for CI/CD
    jnkn diff main HEAD --format json --output diff-report.json
    
    # Generate markdown changelog
    jnkn diff main HEAD --format markdown > CHANGES.md
    
    # Fail CI if breaking changes
    jnkn diff origin/main HEAD --fail-on-breaking
    
    # Only show removed columns (breaking changes)
    jnkn diff main HEAD --breaking-only
    """)


def show_github_actions():
    """Show GitHub Actions integration."""
    print("\n" + "=" * 70)
    print("GITHUB ACTIONS INTEGRATION")
    print("=" * 70)
    
    workflow = '''
name: Schema Change Analysis

on:
  pull_request:
    paths:
      - 'src/**/*.py'

jobs:
  diff-analysis:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history for diff
      
      - name: Analyze Changes
        id: diff
        run: |
          jnkn diff origin/${{ github.base_ref }} HEAD \\
            --format json \\
            --output diff-report.json
        continue-on-error: true
      
      - name: Comment on PR
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const report = JSON.parse(fs.readFileSync('diff-report.json'));
            
            let body = '## 📊 Schema Change Analysis\\n\\n';
            
            if (report.summary.has_breaking_changes) {
              body += '### ⚠️ Breaking Changes Detected\\n\\n';
              body += 'The following columns were **removed**:\\n';
              for (const col of report.column_changes) {
                if (col.type === 'removed') {
                  body += `- \`${col.column}\` (${col.context})\\n`;
                }
              }
            } else {
              body += '✅ No breaking changes detected\\n';
            }
            
            body += '\\n### Summary\\n';
            body += `- Columns added: ${report.summary.columns_added}\\n`;
            body += `- Columns removed: ${report.summary.columns_removed}\\n`;
            
            github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: body
            });
      
      - name: Fail on Breaking Changes
        if: steps.diff.outcome == 'failure'
        run: |
          echo "::error::Breaking schema changes detected"
          exit 1
'''
    print(workflow)


# =============================================================================
# Main
# =============================================================================

def main():
    print("""
    ╔═══════════════════════════════════════════════════════════════════╗
    ║                                                                   ║
    ║   DIFF-AWARE ANALYSIS DEMO                                        ║
    ║   Semantic Change Detection for Data Pipelines                    ║
    ║                                                                   ║
    ╚═══════════════════════════════════════════════════════════════════╝
    
    This demo shows how jnkn detects WHAT changed, not just WHICH files.
    
    Traditional diff:  "etl_job.py was modified (+10, -5 lines)"
    jnkn diff:       "Column 'user_id' was removed from SELECT"
    
    """)
    
    # Run all scenarios
    scenario_1_column_removed()
    scenario_2_column_added()
    scenario_3_transform_changed()
    scenario_4_filter_changed()
    scenario_5_table_source_changed()
    scenario_6_multiple_changes()
    
    # Show integration examples
    show_cli_usage()
    show_github_actions()
    
    print("\n" + "=" * 70)
    print("DEMO COMPLETE")
    print("=" * 70)
    print("""
    Key Takeaways:
    
    1. BREAKING CHANGES (column removed, table removed):
       - Downstream jobs WILL fail
       - Must be caught before merge
       - Requires migration plan
    
    2. SAFE CHANGES (column added):
       - Backward compatible
       - No immediate impact
       - Downstream can adopt when ready
    
    3. DATA CHANGES (filter modified, transform changed):
       - Schema is same, semantics are different
       - May cause data quality issues
       - Harder to detect without semantic analysis
    
    4. LINEAGE CHANGES (source table changed):
       - Fundamental change in data provenance
       - Should trigger data validation
       - May indicate environment issues (prod vs staging)
    
    jnkn's diff analysis catches ALL of these, not just file changes.
    """)


if __name__ == "__main__":
    main()