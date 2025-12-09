"""Class and module-level env var patterns."""
import os


# Module-level constants
DEFAULT_TIMEOUT = int(os.getenv("DEFAULT_TIMEOUT", "30"))
MAX_RETRIES = int(os.environ.get("MAX_RETRIES", "3"))


class Config:
    """Configuration class with class-level env vars."""
    
    # Class attributes
    DATABASE_URL = os.getenv("DATABASE_URL")
    REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
    
    # With type annotation
    api_key: str = os.getenv("API_KEY", "")
    
    def __init__(self):
        # Instance-level (should still be detected)
        self.session_secret = os.getenv("SESSION_SECRET")


class DatabaseConfig:
    """Another config class."""
    
    HOST = os.environ["DB_HOST"]
    PORT = os.environ.get("DB_PORT", "5432")
    NAME = os.getenv("DB_NAME")
