"""Application configuration with multiple env var patterns."""
import os
from os import getenv, environ

# Pattern 1: os.getenv()
DATABASE_HOST = os.getenv("DATABASE_HOST")
DATABASE_PORT = os.getenv("DATABASE_PORT", "5432")

# Pattern 2: os.environ.get()
REDIS_URL = os.environ.get("REDIS_URL")
CACHE_TTL = os.environ.get("CACHE_TTL", "3600")

# Pattern 3: os.environ[]
API_KEY = os.environ["API_KEY"]

# Pattern 4: After from-import
SECRET_KEY = getenv("SECRET_KEY")
DEBUG_MODE = environ.get("DEBUG_MODE", "false")

# Pattern 5: Heuristic (env-like variable names)
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL")
AUTH_TOKEN_SECRET = os.getenv("AUTH_TOKEN_SECRET")

class Config:
    """Config class with env vars."""
    db_host = os.getenv("DB_HOST")
    db_name = os.environ.get("DB_NAME", "myapp")
