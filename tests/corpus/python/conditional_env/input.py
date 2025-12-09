"""
Environment variables used in conditional logic and comprehensions.
"""
import os

# Case 1: Ternary Operator
DEBUG = True if os.getenv("DEBUG") == "true" else False

# Case 2: Boolean OR chain
# This is a very common pattern for fallbacks
DB_HOST = os.getenv("DB_HOST") or os.getenv("DATABASE_HOST") or "localhost"

# Case 3: If statement block
FEATURE_CONFIG = None
if os.getenv("ENABLE_FEATURE"):
    FEATURE_CONFIG = os.getenv("FEATURE_CONFIG_JSON")

# Case 4: List Comprehension
# Constructing a list of hosts from indexed env vars
KAFKA_BROKERS = [
    os.getenv(f"KAFKA_BROKER_{i}") 
    for i in range(3)
]

# Case 5: Walrus Operator (Python 3.8+)
if (token := os.getenv("AUTH_TOKEN")):
    print("Authenticated")

# Case 6: Lambda function
get_db = lambda: os.getenv("DB_CONNECTION_STRING")