"""
python-dotenv patterns.
Specifically targets dictionary usage via dotenv_values().
"""
import os
from dotenv import load_dotenv, dotenv_values

# Standard load (already covered by stdlib tests, but good for regression)
load_dotenv()
standard_var = os.getenv("STANDARD_VAR")

# Case 1: dotenv_values() dictionary access
config = dotenv_values(".env")
db_host = config["DATABASE_HOST"]
db_port = config.get("DATABASE_PORT", "5432")

# Case 2: Inline usage
secret = dotenv_values()["API_SECRET"]

# Case 3: With specific path
test_config = dotenv_values(".env.test")
test_db = test_config["TEST_DB_URL"]

# Case 4: Override flag (doesn't introduce new vars, but shouldn't crash)
load_dotenv(override=True)