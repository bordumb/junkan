"""
Demo Manager - Scaffolds a minimal example project.

Creates a focused demo that tells one clear story:
"A developer renames a Terraform output and jnkn catches it."

The demo has just 3 files:
- app.py: Python code that reads DATABASE_URL from environment
- main.tf: Terraform that provisions RDS and outputs the connection string
- deployment.yaml: K8s deployment that wires them together

The breaking change: Renaming the Terraform output from `database_url`
to `db_connection_string` - a common refactoring mistake that breaks
production if not caught.
"""

import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


class DemoManager:
    """Manages the creation of the demo environment."""

    # =========================================================================
    # Python Application
    # =========================================================================
    APP_PY = '''
"""Payment processing service."""
import os

# Database connection - provided by Terraform
DATABASE_URL = os.getenv("DATABASE_URL")

# Redis cache - provided by Terraform
REDIS_URL = os.getenv("REDIS_URL")

# API key - provided by K8s Secret
API_KEY = os.getenv("API_KEY")


def main():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL not configured!")

    print(f"Connecting to database...")
    print(f"Cache: {REDIS_URL}")


if __name__ == "__main__":
    main()
'''

    # =========================================================================
    # Terraform Infrastructure - V1 (Working State)
    # =========================================================================
    TERRAFORM_V1 = """
# Payment service infrastructure

resource "aws_db_instance" "main" {
  identifier     = "payment-db"
  engine         = "postgres"
  instance_class = "db.t3.micro"
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id = "payment-cache"
  engine     = "redis"
}

# ✅ This output matches DATABASE_URL in app.py
output "database_url" {
  value       = "postgres://${aws_db_instance.main.endpoint}/payments"
  description = "PostgreSQL connection string"
}

# ✅ This output matches REDIS_URL in app.py
output "redis_url" {
  value = "redis://${aws_elasticache_cluster.redis.cache_nodes.0.address}:6379"
}
"""

    # =========================================================================
    # Terraform Infrastructure - V2 (Breaking Change!)
    # =========================================================================
    TERRAFORM_V2_BREAKING = """
# Payment service infrastructure

resource "aws_db_instance" "main" {
  identifier     = "payment-db"
  engine         = "postgres"
  instance_class = "db.t3.micro"
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id = "payment-cache"
  engine     = "redis"
}

# ❌ BREAKING CHANGE: Renamed from "database_url" to "db_connection_string"
#    app.py still expects DATABASE_URL - this will cause a production outage!
output "db_connection_string" {
  value       = "postgres://${aws_db_instance.main.endpoint}/payments"
  description = "PostgreSQL connection string"
}

# ✅ This output still matches REDIS_URL in app.py
output "redis_url" {
  value = "redis://${aws_elasticache_cluster.redis.cache_nodes.0.address}:6379"
}
"""

    # =========================================================================
    # Kubernetes Deployment
    # =========================================================================
    K8S_DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
  namespace: default
spec:
  replicas: 3
  template:
    spec:
      containers:
        - name: app
          image: payment-service:latest
          env:
            # Wired to Terraform output (via external-secrets or similar)
            - name: DATABASE_URL
              value: "$(DATABASE_URL)"  # Placeholder - replaced at deploy time

            - name: REDIS_URL
              value: "$(REDIS_URL)"

            # From K8s Secret
            - name: API_KEY
              valueFrom:
                secretKeyRef:
                  name: payment-secrets
                  key: api-key
"""

    # =========================================================================
    # Manifest (jnkn.toml) for Multi-Repo support
    # =========================================================================
    JNKN_TOML = """
[project]
name = "payment-service"
version = "1.0.0"

[dependencies]
# Points to the sibling infrastructure directory
infrastructure = { path = "../infrastructure" }
"""

    # =========================================================================
    # README for the demo
    # =========================================================================
    README = """
# jnkn Demo: Catch Breaking Changes

This demo shows how jnkn detects breaking changes across your stack.

## The Scenario

1. **main branch**: Everything works. Terraform outputs match what app.py expects.

2. **feature/refactor-outputs branch**: A developer renamed `database_url` to
   `db_connection_string` in Terraform. Seems harmless, right?

3. **The Problem**: `app.py` still expects `DATABASE_URL`. Without jnkn, this
   ships to production and causes an outage.

## Try It

1. Open `src/app.py` in VS Code
2. Notice `DATABASE_URL` has a red squiggly line
3. Hover over it to see: "Orphaned Environment Variable: no infrastructure provider"

## The Fix

Either:
- Rename the Terraform output back to `database_url`
- Update `app.py` to use `DB_CONNECTION_STRING`

jnkn caught this before it hit production! 🎉

## Development Workflow

If using this demo to develop `jnkn` itself, run this to get setup:
```bash
python -m venv .venv
.venv/bin/pip install -e /path/to/junkan/packages/jnkn-core
.venv/bin/pip install -e /path/to/junkan/packages/jnkn-lsp
"""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def _run_git(self, cwd: Path, args: list[str]) -> None:
        """Run a git command in the demo directory."""
        try:
            subprocess.run(
                ["git"] + args,
                cwd=cwd,
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"Git command failed: {e.stderr}")

    def provision(self, multirepo: bool = False) -> Path:
        """
        Create the demo project structure.

        Args:
            multirepo: If True, creates separate directories for app and infra
                      linked by jnkn.toml.

        Returns:
            Returns the path to the primary working directory (app dir in multirepo).
        """
        base_dir = self.root_dir / "jnkn-demo"

        # Clean up existing demo
        if base_dir.exists():
            shutil.rmtree(base_dir)

        base_dir.mkdir(parents=True)

        if multirepo:
            return self._provision_multirepo(base_dir)
        else:
            return self._provision_monorepo(base_dir)

    def _provision_monorepo(self, demo_dir: Path) -> Path:
        """Standard single-directory demo."""
        (demo_dir / "src").mkdir()
        (demo_dir / "terraform").mkdir()
        (demo_dir / "k8s").mkdir()

        # Step 1: Create V1 (working state)
        (demo_dir / "src" / "app.py").write_text(self.APP_PY.strip())
        (demo_dir / "terraform" / "main.tf").write_text(self.TERRAFORM_V1.strip())
        (demo_dir / "k8s" / "deployment.yaml").write_text(self.K8S_DEPLOYMENT.strip())
        (demo_dir / "README.md").write_text(self.README.strip())

        # Initialize git
        self._init_git_repo(demo_dir)

        # Step 2: Create feature branch with breaking change
        self._run_git(demo_dir, ["checkout", "-b", "feature/refactor-outputs"])
        (demo_dir / "terraform" / "main.tf").write_text(self.TERRAFORM_V2_BREAKING.strip())
        self._run_git(demo_dir, ["add", "."])
        self._run_git(demo_dir, ["commit", "-m", "refactor: rename database output"])

        logger.info(f"✨ Demo created at: {demo_dir}")
        return demo_dir

    def _provision_multirepo(self, base_dir: Path) -> Path:
        """Multi-repository demo structure."""
        app_dir = base_dir / "payment-service"
        infra_dir = base_dir / "infrastructure"

        app_dir.mkdir()
        infra_dir.mkdir()

        # APP REPO
        (app_dir / "src").mkdir()
        (app_dir / "src" / "app.py").write_text(self.APP_PY.strip())
        (app_dir / "jnkn.toml").write_text(self.JNKN_TOML.strip())
        (app_dir / "README.md").write_text(self.README.strip())

        # INFRA REPO
        (infra_dir / "terraform").mkdir()
        # Note: We write the BREAKING change immediately for the multirepo demo
        # to show how cross-repo detection works immediately upon scan.
        (infra_dir / "terraform" / "main.tf").write_text(self.TERRAFORM_V2_BREAKING.strip())

        # Init git for both (simulating separate repos)
        self._init_git_repo(app_dir, message="Initial app commit")
        self._init_git_repo(infra_dir, message="Initial infra commit")

        logger.info(f"✨ Multi-repo demo created at: {base_dir}")
        logger.info(f"   App:   {app_dir}")
        logger.info(f"   Infra: {infra_dir}")
        logger.info("   Dependencies linked via jnkn.toml in payment-service/")

        return app_dir

    def _init_git_repo(self, path: Path, message: str = "Initial commit") -> None:
        """Initialize a git repository at the path."""
        self._run_git(path, ["init", "--initial-branch=main"])
        self._run_git(path, ["config", "user.email", "demo@jnkn.dev"])
        self._run_git(path, ["config", "user.name", "jnkn Demo"])
        self._run_git(path, ["add", "."])
        self._run_git(path, ["commit", "-m", message])


def create_demo_manager(root_dir: Path) -> DemoManager:
    """Factory function for creating a DemoManager."""
    return DemoManager(root_dir)
