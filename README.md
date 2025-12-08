# Junkan

**The "Pre-Flight" Impact Analysis Engine for Engineering Teams.**

Junkan prevents production outages by stitching together the hidden dependencies between your **Infrastructure** (Terraform), **Data Pipelines** (dbt), and **Application Code**.

## The Problem

Most tools operate in silos:
* *Infracost* checks Terraform cost.
* *dbt* checks SQL lineage.
* *Turborepo* checks code monorepos.

**Junkan checks the "Glue".** It detects cross-domain breaking changes, like:
* **Infra $\rightarrow$ Code:** A Terraform PR renames an environment variable `DB_HOST` to `DATABASE_HOST`, silently causing your Python application to crash on startup.
* **Infra $\rightarrow$ Data:** A Terraform change rotates the IAM role for an S3 bucket, inadvertently revoking the `s3:GetObject` permission used by a dbt model to load raw CSVs, causing the nightly ETL to fail.
* **Data $\rightarrow$ Code:** A dbt model schema change renames the `user_id` column to `customer_id` in the `fct_orders` table, but the Python backend service that queries this table for the "Order History" API endpoint wasn't updated, leading to 500 errors.
* **Code $\rightarrow$ Infra:** A developer updates the `docker-compose.yml` or Kubernetes manifest to use a new Redis image version (e.g., v7), but the Terraform state still provisions an older AWS ElastiCache parameter group incompatible with v7, preventing the service from stabilizing.
* **Data $\rightarrow$ Infra:** A new dbt model logic change causes a table to triple in size overnight, exceeding the allocated storage IOPS defined in the Terraform configuration for the RDS instance, leading to severe latency.
* **Infra $\rightarrow$ Code:** A Terraform PR deletes a deprecated SQS queue, but a legacy Python background worker still has a hardcoded reference to that queue URL in its settings, causing the worker to crash loop on startup.

---

## Prerequisites

* **Python 3.11+**
* **[uv](https://github.com/astral-sh/uv)** (Required for dependency management)

## Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-org/junkan.git](https://github.com/your-org/junkan.git)
    cd junkan
    ```

2.  **Install dependencies:**
    Junkan uses `uv` to manage the virtual environment and dependencies instantly.
    ```bash
    uv sync
    ```

3.  **Verify installation:**
    Run the help command to ensure the CLI is ready.
    ```bash
    uv run junkan --help
    ```

---

## Quick Start

### 1. Ingest Your Artifacts
Junkan works by building a local dependency graph (stored in SQLite) from your build artifacts. It does not connect to your cloud provider; it parses the plans you generate.

**Generate standard artifacts:**
```bash
# 1. Terraform
terraform plan -out=tfplan
terraform show -json tfplan > tfplan.json

# 2. dbt
dbt compile  # Generates target/manifest.json
````

**Ingest them into Junkan:**

```bash
uv run junkan ingest \
  --tf-plan tfplan.json \
  --dbt-manifest target/manifest.json
```

*Output: `{"status": "success", "relationships_ingested": 142}`*

### 2\. Calculate Blast Radius

Once the graph is built, you can query it to see the downstream impact of changing any resource.

```bash
# Example: What happens if I modify the 'users' table?
uv run junkan blast-radius "model.users"
```

**Sample Output:**

```json
{
  "source_artifacts": ["model.users"],
  "total_impacted_count": 5,
  "impacted_artifacts": [
    "model.monthly_revenue",
    "src/payment_service/user_lookup.py",
    "aws_lambda_function.daily_report"
  ],
  "breakdown": {
    "data": ["model.monthly_revenue"],
    "code": ["src/payment_service/user_lookup.py"],
    "infra": ["aws_lambda_function.daily_report"],
    "unknown": []
  }
}
```

## Running as a GitHub Action

Junkan is designed to run in CI to block dangerous PRs.

```yaml
# .github/workflows/junkan-check.yml
name: Junkan Impact Analysis
on: [pull_request]

jobs:
  analyze:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      # 1. Generate artifacts (Terraform/dbt)
      - run: make plan
      
      # 2. Run Junkan
      - uses: your-org/junkan@v2
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
```

## Contributing

1.  Make changes in `src/junkan/`.
2.  Run `uv sync` to update environment.
3.  Run tests (coming soon).
