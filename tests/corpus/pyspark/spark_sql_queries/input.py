"""PySpark SQL query patterns."""
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("SQLJob").getOrCreate()

# Simple SELECT
users = spark.sql("SELECT * FROM analytics.dim_users WHERE active = true")

# JOIN query
events = spark.sql("""
    SELECT 
        u.user_id,
        u.email,
        e.event_type,
        e.created_at
    FROM analytics.dim_users u
    JOIN analytics.fact_events e ON u.user_id = e.user_id
    WHERE e.created_at > '2024-01-01'
""")

# INSERT INTO
spark.sql("""
    INSERT INTO analytics.daily_summary
    SELECT date, count(*) as event_count
    FROM analytics.fact_events
    GROUP BY date
""")

# CREATE TABLE AS SELECT
spark.sql("""
    CREATE TABLE IF NOT EXISTS analytics.user_segments AS
    SELECT user_id, segment
    FROM analytics.dim_users
    WHERE segment IS NOT NULL
""")

# MERGE INTO (Delta Lake)
spark.sql("""
    MERGE INTO analytics.dim_users target
    USING staging.user_updates source
    ON target.user_id = source.user_id
    WHEN MATCHED THEN UPDATE SET *
    WHEN NOT MATCHED THEN INSERT *
""")
