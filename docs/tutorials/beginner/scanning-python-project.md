# Scanning a Python Project

Learn to detect environment variables in a Python application.

**Time:** 10 minutes

## Prerequisites

- Jnkn installed (`pip install jnkn[full]`)
- A Python project (or use our example)

## Setup

If you don't have a project, create a sample:

```bash
mkdir jnkn-tutorial && cd jnkn-tutorial
```

Create `app/config.py`:

```python
import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    api_key: str
    debug: bool = False
    
    class Config:
        env_prefix = "APP_"

settings = Settings()

# Also using direct env access
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

Create `app/main.py`:

```python
from config import settings, REDIS_URL
import os

def get_db_connection():
    return connect(os.getenv("DATABASE_URL"))  # Different from settings!

def get_cache():
    return Redis.from_url(REDIS_URL)
```

## Scan

```bash
jnkn init
jnkn scan
```

Output:

```
🔍 Scanning /path/to/jnkn-tutorial
📁 Found 2 Python files
✅ Parsed 8 nodes, 6 edges

Detected Environment Variables:
  env:APP_DATABASE_URL     (pydantic_settings)
  env:APP_API_KEY          (pydantic_settings)  
  env:APP_DEBUG            (pydantic_settings)
  env:REDIS_URL            (os.getenv)
  env:LOG_LEVEL            (os.environ.get)
  env:DATABASE_URL         (os.getenv)
```

## Understanding the Output

Jnkn detected **6 environment variables** from multiple patterns:

| Variable | Source | Pattern |
|----------|--------|---------|
| `APP_DATABASE_URL` | Pydantic Settings | `env_prefix + field_name` |
| `APP_API_KEY` | Pydantic Settings | `env_prefix + field_name` |
| `APP_DEBUG` | Pydantic Settings | `env_prefix + field_name` |
| `REDIS_URL` | Direct access | `os.getenv()` |
| `LOG_LEVEL` | Direct access | `os.environ.get()` |
| `DATABASE_URL` | Direct access | `os.getenv()` |

!!! warning "Potential Bug Detected"
    Notice `DATABASE_URL` and `APP_DATABASE_URL` — these might be the same intent but different names. Jnkn helps you spot these inconsistencies.

## View the Graph

```bash
jnkn stats
```

```
📊 Graph Statistics
═══════════════════════════════════
Nodes by Type:
  code_file:    2
  env_var:      6

Edges by Type:
  reads:        6
```

## Explore Dependencies

Which files read `REDIS_URL`?

```bash
jnkn blast env:REDIS_URL
```

```json
{
  "source": "env:REDIS_URL",
  "impacted": ["file://app/config.py"],
  "total_impacted": 1
}
```

## Supported Python Patterns

Jnkn detects these patterns automatically:

| Pattern | Example |
|---------|---------|
| `os.getenv()` | `os.getenv("VAR")` |
| `os.environ.get()` | `os.environ.get("VAR")` |
| `os.environ[]` | `os.environ["VAR"]` |
| Pydantic Settings | `class Config(BaseSettings)` |
| Pydantic Field | `Field(env="VAR")` |
| Click/Typer | `@click.option(envvar="VAR")` |
| django-environ | `env.str("VAR")` |

See [Python Patterns Reference](../../reference/patterns/python-env-vars.md) for the full list.

## Next Steps

- [:octicons-arrow-right-24: Understanding Blast Radius](understanding-blast-radius.md)
- [:octicons-arrow-right-24: Add Terraform to your scan](../intermediate/multi-stack-analysis.md)
