"""
F-string interpolation containing environment variable calls.
Common for constructing URLs or connection strings.
"""
import os

# Case 1: Simple interpolation
API_URL = f"https://{os.getenv('API_HOST')}/v1"

# Case 2: Multiple interpolations
DB_CONN = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASS')}@{os.getenv('DB_HOST')}:5432/db"

# Case 3: With method calls inside
# .upper() is called on the result of getenv
LOG_FILE = f"/var/log/app_{os.getenv('ENV_NAME', 'dev').lower()}.log"

# Case 4: Nested quotes
# This is tricky parsing but valid python
MESSAGE = f"Welcome to {os.environ.get('APP_NAME', 'Default App')}"

# Case 5: Multiline f-string
CONFIG = f"""
    service_name: {os.getenv('SERVICE_NAME')}
    replica_count: {os.getenv('REPLICA_COUNT', '1')}
"""