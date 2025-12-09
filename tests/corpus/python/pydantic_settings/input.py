"""Pydantic Settings - common pattern in modern Python apps."""
from pydantic_settings import BaseSettings
from pydantic import Field


class DatabaseSettings(BaseSettings):
    """Database configuration from environment."""
    
    host: str = Field(default="localhost")
    port: int = Field(default=5432)
    name: str = Field(default="myapp")
    user: str
    password: str
    
    class Config:
        env_prefix = "DB_"


class AppSettings(BaseSettings):
    """Main application settings."""
    
    debug: bool = Field(default=False)
    secret_key: str
    api_key: str = Field(default="")
    
    # Nested alias
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    class Config:
        env_prefix = "APP_"


# Usage
settings = AppSettings()
db = DatabaseSettings()
