"""File-based data sources (parquet, delta, csv, etc.)."""
from pyspark.sql import SparkSession
from delta.tables import DeltaTable

spark = SparkSession.builder.appName("FileIOJob").getOrCreate()

# Read parquet
raw_events = spark.read.parquet("s3://data-lake/raw/events/")

# Read CSV with options
config = spark.read.csv("s3://data-lake/config/mappings.csv")

# Read Delta format
delta_df = spark.read.format("delta").load("s3://data-lake/delta/users")

# Read JSON
json_data = spark.read.json("hdfs://cluster/data/json/metadata.json")

# DeltaTable API
delta_table = DeltaTable.forPath(spark, "s3://data-lake/delta/transactions")
delta_named = DeltaTable.forName(spark, "catalog.schema.customers")

# Write parquet
raw_events.write.mode("overwrite").parquet("s3://data-lake/processed/events/")

# Write Delta
delta_df.write.format("delta").mode("append").save("s3://data-lake/delta/users_v2")

# Write CSV
config.write.csv("s3://data-lake/exports/config_backup.csv")
