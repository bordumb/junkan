"""
Apache Airflow Variable patterns.
Airflow Variables often map to environment variables or secret backends.
"""
from airflow.models import Variable
from airflow.hooks.base import BaseHook

# Case 1: Simple Get
api_key = Variable.get("API_KEY")

# Case 2: Get with JSON deserialization
config = Variable.get("ETL_CONFIG", deserialize_json=True)

# Case 3: Get with default
timeout = Variable.get("TASK_TIMEOUT", default_var=300)

def processing_task():
    # Case 4: Inside function scope
    conn_id = Variable.get("SNOWFLAKE_CONN_ID")
    return conn_id

# Case 5: Connection get_connection (related, often env vars)
# URI format often contains env var refs, but the key itself is the ID
conn = BaseHook.get_connection("aws_default")