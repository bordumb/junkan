"""Basic os.getenv patterns - the foundation."""
import os

# Pattern 1: Simple os.getenv
DATABASE_HOST = os.getenv("DATABASE_HOST")

# Pattern 2: os.getenv with default
DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")

# Pattern 3: os.environ.get
REDIS_URL = os.environ.get("REDIS_URL")

# Pattern 4: os.environ.get with default
CACHE_TTL = os.environ.get("CACHE_TTL", "3600")

# Pattern 5: os.environ[] direct access
API_KEY = os.environ["API_KEY"]

# Pattern 6: Nested in function call
print(os.getenv("DEBUG_MODE", "false"))
