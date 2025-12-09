"""
Real-world ETL job pattern.
Reads from multiple sources, transforms, writes to multiple targets.
"""
import os
from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# Configuration from environment
DATABASE_HOST = os.getenv("DATABASE_HOST")
OUTPUT_PATH = os.getenv("OUTPUT_PATH", "s3://data-lake/output/")

spark = SparkSession.builder \
    .appName("DailyUserMetrics") \
    .config("spark.sql.shuffle.partitions", "200") \
    .getOrCreate()

# ============================================================================
# EXTRACT: Read from multiple sources
# ============================================================================

# User dimension table
dim_users = spark.read.table("warehouse.dim_users")

# Event facts from Delta Lake
fact_events = spark.read.format("delta").load("s3://data-lake/delta/fact_events")

# External reference data
geo_lookup = spark.read.parquet("s3://reference-data/geo/countries.parquet")

# Recent campaign data via SQL
campaigns = spark.sql("""
    SELECT campaign_id, campaign_name, start_date, end_date
    FROM marketing.campaigns
    WHERE status = 'active'
""")

# ============================================================================
# TRANSFORM: Business logic
# ============================================================================

# Join users with events
user_events = dim_users.join(
    fact_events,
    dim_users.user_id == fact_events.user_id,
    "left"
)

# Enrich with geo data
enriched = user_events.join(
    geo_lookup,
    user_events.country_code == geo_lookup.code,
    "left"
)

# Aggregate daily metrics
daily_metrics = enriched.groupBy(
    F.col("user_id"),
    F.to_date("event_timestamp").alias("date")
).agg(
    F.count("*").alias("event_count"),
    F.countDistinct("session_id").alias("session_count"),
    F.sum("revenue").alias("total_revenue")
)

# Calculate user segments
user_segments = daily_metrics.withColumn(
    "segment",
    F.when(F.col("total_revenue") > 1000, "high_value")
     .when(F.col("total_revenue") > 100, "medium_value")
     .otherwise("low_value")
)

# ============================================================================
# LOAD: Write to multiple targets
# ============================================================================

# Write to warehouse table
user_segments.write \
    .mode("overwrite") \
    .partitionBy("date") \
    .saveAsTable("warehouse.daily_user_metrics")

# Write to Delta Lake for ML team
user_segments.write \
    .format("delta") \
    .mode("append") \
    .save("s3://ml-features/user_segments/")

# Write summary to reporting database
summary = user_segments.groupBy("date", "segment").count()
summary.write \
    .mode("append") \
    .insertInto("reporting.segment_summary")

# Export for external partners
user_segments.select("user_id", "date", "segment") \
    .write \
    .mode("overwrite") \
    .parquet(f"{OUTPUT_PATH}/partner_export/")

spark.stop()
