# jnkn

**The Pre-Flight Impact Analysis Engine for Engineering Teams.**

[![PyPI version](https://badge.fury.io/py/jnkn.svg)](https://badge.fury.io/py/jnkn)
[![Documentation](https://img.shields.io/badge/docs-docs.jnkn.io-blue)](https://bordumb.github.io/jnkn/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**jnkn** (pronounced "jun-kan") prevents production outages by stitching together the hidden dependencies between your **Infrastructure** (Terraform), **Data Pipelines** (dbt), and **Application Code** (Python/JS).

---

## 📚 [Read the Full Documentation](https://bordumb.github.io/jnkn/)

---

## The Blind Spot

Most tools operate in silos. Terraform sees resources, dbt sees tables, code sees imports. **jnkn sees the glue.**

It detects the invisible, cross-domain breaking changes that slip through every other tool:

```mermaid
graph LR
    subgraph "The Gap"
        TF[Terraform Change] --"Breaks"--> CODE[App Configuration]
        CODE --"Breaks"--> DATA[Data Pipeline]
    end
    
    style TF fill:#ff6b6b,color:#fff
    style DATA fill:#ff6b6b,color:#fff
````

## 🚀 Quick Start

Get running in less than 2 minutes.

### 1\. Installation

```bash
pip install jnkn
```

### 2\. Initialize & Scan

Navigate to your project root (monorepo or service).

```bash
# Detects your stack (Python, Terraform, etc.)
jnkn init

# Builds the dependency graph
jnkn scan
```

### 3\. Find Impact

Simulate a change to see what breaks downstream.

```bash
# If I rename this env var, what code breaks?
jnkn blast env:DATABASE_URL

# If I modify this Terraform resource, what app fails?
jnkn blast infra:payment_db_host
```

-----

## 🤖 CI/CD Integration

Block breaking changes in Pull Requests before they merge.

```yaml
# .github/workflows/jnkn.yml
steps:
  - uses: actions/checkout@v4
  - name: Run Jnkan Gate
    run: |
      pip install jnkn
      # Blocks if critical dependencies are broken
      jnkn check --git-diff origin/main HEAD
```

-----

## Supported Stacks

| Domain | Supported Patterns |
|--------|-------------------|
| **Python** | `os.getenv`, Pydantic Settings, Click/Typer, django-environ |
| **Terraform** | Resources, variables, outputs, data sources |
| **Kubernetes** | ConfigMaps, Secrets, environment variables |
| **dbt** | `ref()`, `source()`, manifest parsing |
| **JavaScript** | `process.env`, dotenv, Vite |

-----

## Contributing

We welcome contributions\! Please see our [Contributing Guide](https://www.google.com/search?q=https://docs.jnkn.io/community/contributing/) for details on how to set up your development environment.

## License

MIT