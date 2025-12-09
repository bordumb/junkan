"""ETL job that matches the spark.yml configuration."""
import os
from pyspark.sql import SparkSession

DATABASE_HOST = os.getenv("DATABASE_HOST")
S3_BUCKET = os.getenv("S3_BUCKET")

spark = SparkSession.builder.appName("UserMetrics").getOrCreate()

# Read input (matches spark.yml inputs)
users = spark.read.table("warehouse.dim_users")

# Additional read not in YAML
events = spark.read.parquet(f"s3://{S3_BUCKET}/raw/events/")

# Transform
metrics = users.join(events, "user_id").groupBy("user_id").count()

# Write output (matches spark.yml outputs)
metrics.write.saveAsTable("warehouse.daily_metrics")

# Additional write not in YAML
metrics.write.parquet(f"s3://{S3_BUCKET}/exports/metrics/")
