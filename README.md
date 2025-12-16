
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
    subgraph "The Blind Spot"
        TF[Terraform Change] --"Breaks"--> CODE[App Configuration]
        CODE --"Breaks"--> DATA[Data Pipeline]
    end
    
    style TF fill:#ff6b6b,color:#fff
    style DATA fill:#ff6b6b,color:#fff
````

-----

## 🧠 Two-Tier Architecture

Jnkn is built on a split architecture to provide **stability for CI/CD** while enabling **intelligence for AI Agents**.

| Component | **Jnkn Core** (`jnkn`) | **Jnkn AI** (`jnkn-mcp`) |
| :--- | :--- | :--- |
| **Role** | **The Ground Truth** | **The Navigator** |
| **Philosophy** | Deterministic, 100% Local, Strict | Probabilistic, Context-Aware, Flexible |
| **Use Case** | CI/CD Gating, Breaking Change Detection | AI Context, Architecture Q\&A, Refactoring |
| **Output** | Pass/Fail, Static Risk Reports | LLM Context (MCP), Semantic Explanations |
| **Connectivity** | Offline / Air-gapped | Connects to LLMs / Vector Stores |

-----

## 🚀 Quick Start (Core)

Get protection in less than 2 minutes.

### 1\. Installation

```bash
pip install jnkn
```

### 2\. Initialize

Navigate to your project root. `jnkn` will automatically detect your stack (Python, Terraform, Kubernetes, etc.) and configure itself.

```bash
jnkn init
```

### 3\. Check Impact

Run a check to see if your current changes break any downstream dependencies.

```bash
# Checks your current changes against the main branch
jnkn check
```

**That's it**. If you renamed a Terraform output that your app relies on, `jnkn` check will fail the build and tell you exactly what broke.

-----

## 🤖 AI Integration (MCP)

Jnkn exposes your repository's dependency graph via the **Model Context Protocol (MCP)**. This allows AI agents (Claude Desktop, Cursor, Windsurf) to "chat with your architecture."

### Setup

```bash
pip install jnkn-mcp
```

### Capabilities

  * **Smart Refactoring:** Ask your AI, *"If I rename `DB_HOST` in Terraform, what code breaks?"* The AI queries `jnkn` for the exact blast radius.
  * **Architecture Q\&A:** Ask, *"Show me every service that consumes the payment database."*
  * **Impact-Aware Agents:** Give your AI agents the `check_impact` tool so they self-correct before writing broken code.

-----

## ⚡ CI/CD Integration

Block breaking changes in Pull Requests before they merge.

```yaml
# .github/workflows/jnkn.yml
steps:
  - uses: actions/checkout@v4
    with:
      fetch-depth: 0  # Required for diff analysis
      
  - name: Run Jnkn Gate
    run: |
      pip install jnkn
      # Fails if critical dependencies are broken
      jnkn check --git-diff origin/main HEAD --fail-if-critical
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

We welcome contributions\! Please see our [Contributing Guide](https://bordumb.github.io/jnkn/community/contributing/) for details on how to set up your development environment.

Installing from source:
```bash
uv pip install -e packages/jnkn-core
uv pip install -e packages/jnkn-lsp
```

## License

MIT
