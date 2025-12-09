"""Pydantic settings example."""
from pydantic import BaseSettings, Field

class Settings(BaseSettings):
    """Application settings from environment."""
    
    database_url: str = Field(..., env="DATABASE_URL")
    redis_host: str = Field("localhost", env="REDIS_HOST")
    api_secret: str = Field(..., env="API_SECRET_KEY")
    
    class Config:
        env_prefix = "APP_"
