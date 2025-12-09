# Python Environment Variable Patterns

All Python patterns Jnkn detects.

## Standard Library

### `os.getenv()`

```python
# ✅ Detected
os.getenv("DATABASE_URL")
os.getenv("DATABASE_URL", "default")
os.getenv("DATABASE_URL", default="default")

# ❌ Not detected (dynamic key)
key = "DATABASE_URL"
os.getenv(key)
```

### `os.environ.get()`

```python
# ✅ Detected
os.environ.get("DATABASE_URL")
os.environ.get("DATABASE_URL", "default")

# ❌ Not detected
os.environ.get(key)
```

### `os.environ[]`

```python
# ✅ Detected
os.environ["DATABASE_URL"]

# ❌ Not detected
os.environ[key]
```

### From-imports

```python
from os import getenv, environ

# ✅ Detected
getenv("DATABASE_URL")
environ.get("DATABASE_URL")
environ["DATABASE_URL"]
```

## Pydantic Settings

### BaseSettings Fields

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ✅ Detected as env:DATABASE_URL
    database_url: str
    
    # ✅ Detected as env:API_KEY
    api_key: str = "default"
    
    # ✅ Detected as env:DEBUG
    debug: bool = False
```

### Field with `env=`

```python
from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # ✅ Detected as env:DB_URL (explicit override)
    database_url: str = Field(env="DB_URL")
    
    # ✅ Detected as env:MY_API_KEY
    api_key: str = Field(env="MY_API_KEY")
```

### `env_prefix`

```python
class Settings(BaseSettings):
    # ✅ Detected as env:APP_DATABASE_URL
    database_url: str
    
    # ✅ Detected as env:APP_DEBUG
    debug: bool = False
    
    class Config:
        env_prefix = "APP_"
```

### `model_config`

```python
class Settings(BaseSettings):
    database_url: str  # ✅ env:MYAPP_DATABASE_URL
    
    model_config = SettingsConfigDict(env_prefix="MYAPP_")
```

## Click / Typer

### Click `envvar=`

```python
import click

@click.command()
@click.option("--host", envvar="API_HOST")  # ✅ Detected
@click.option("--port", envvar="API_PORT", type=int)  # ✅ Detected
@click.option("--db", envvar=["DB_URL", "DATABASE_URL"])  # ✅ Both detected
def main(host, port, db):
    pass
```

### Typer `envvar=`

```python
import typer

app = typer.Typer()

@app.command()
def main(
    host: str = typer.Option(..., envvar="API_HOST"),  # ✅ Detected
    port: int = typer.Option(8080, envvar="API_PORT"),  # ✅ Detected
):
    pass
```

## django-environ

### `environ.Env()`

```python
import environ

env = environ.Env()

# ✅ All detected
DEBUG = env("DEBUG")
DATABASE_URL = env.db("DATABASE_URL")
SECRET_KEY = env.str("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")
CACHE_URL = env.cache("CACHE_URL")
```

### Type Methods

| Method | Example | Detected As |
|--------|---------|-------------|
| `env()` | `env("VAR")` | `env:VAR` |
| `env.str()` | `env.str("VAR")` | `env:VAR` |
| `env.bool()` | `env.bool("VAR")` | `env:VAR` |
| `env.int()` | `env.int("VAR")` | `env:VAR` |
| `env.float()` | `env.float("VAR")` | `env:VAR` |
| `env.list()` | `env.list("VAR")` | `env:VAR` |
| `env.dict()` | `env.dict("VAR")` | `env:VAR` |
| `env.url()` | `env.url("VAR")` | `env:VAR` |
| `env.db()` | `env.db("VAR")` | `env:VAR` |
| `env.cache()` | `env.cache("VAR")` | `env:VAR` |

## python-dotenv

### `dotenv_values()`

```python
from dotenv import dotenv_values

config = dotenv_values(".env")

# ✅ Detected
DATABASE_URL = config["DATABASE_URL"]
API_KEY = config.get("API_KEY")
```

## environs

```python
from environs import Env

env = Env()
env.read_env()

# ✅ All detected
DEBUG = env.bool("DEBUG")
DATABASE_URL = env.str("DATABASE_URL")
PORT = env.int("PORT", 8080)
```

## Heuristic Detection

Jnkn uses heuristics for patterns that look like env vars:

```python
# ✅ Detected (heuristic, lower confidence)
DATABASE_URL = some_config.get("DATABASE_URL")
API_KEY = settings["API_KEY"]

# These variable names suggest env vars:
# *_URL, *_HOST, *_PORT, *_KEY, *_SECRET, *_TOKEN, *_PASSWORD
```

## Not Detected

```python
# ❌ Dynamic keys
key = "DATABASE_URL"
os.getenv(key)

# ❌ Computed keys
os.getenv(f"PREFIX_{suffix}")

# ❌ Comments
# os.getenv("DATABASE_URL")

# ❌ Strings
doc = 'Use os.getenv("DATABASE_URL")'

# ❌ Different module named os
import mypackage.os as os
os.getenv("VAR")  # Not stdlib
```
