"""Basic PySpark read/write patterns."""
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("BasicJob").getOrCreate()

# Read from tables
users_df = spark.read.table("marketing.users")
events_df = spark.table("marketing.events")

# Join and transform
joined = users_df.join(events_df, "user_id")
result = joined.groupBy("user_id").count()

# Write output
result.write.mode("overwrite").saveAsTable("marketing.user_event_counts")
