"""Tests env var detection after from-imports."""
from os import getenv, environ

# After 'from os import getenv'
SECRET_KEY = getenv("SECRET_KEY")
JWT_SECRET = getenv("JWT_SECRET", "dev-secret")

# After 'from os import environ'
LOG_LEVEL = environ.get("LOG_LEVEL", "INFO")
WORKER_COUNT = environ["WORKER_COUNT"]
