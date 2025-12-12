"""
Demo Manager - Scaffolds a perfect example project.

This module provides the logic to generate a demo repository structure
that showcases Jnkan's cross-domain stitching capabilities. It creates
files with intentional dependencies between Python, Terraform, and Kubernetes
to ensure the user sees immediate value during their first scan.
"""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class DemoManager:
    """
    Manages the creation of the demo environment.
    """

    # Python code that uses env vars
    APP_PY = """
import os
import logging

# CRITICAL: This connects to the database provisioned in Terraform
DB_HOST = os.getenv("PAYMENT_DB_HOST")
DB_PORT = os.getenv("PAYMENT_DB_PORT", "5432")

def connect():
    if not DB_HOST:
        raise ValueError("Database host not configured!")
    print(f"Connecting to {DB_HOST}:{DB_PORT}...")
"""

    # Terraform that provides those values
    INFRA_TF = """
resource "aws_db_instance" "payment_db" {
  identifier = "payment-db-prod"
  instance_class = "db.t3.micro"
  allocated_storage = 20
  engine = "postgres"
}

# The name 'payment_db_host' matches the Python env var 'PAYMENT_DB_HOST'
# via token matching (payment, db, host)
output "payment_db_host" {
  value = aws_db_instance.payment_db.address
  description = "The endpoint for the payment database"
}

output "payment_db_port" {
  value = aws_db_instance.payment_db.port
}
"""

    # Kubernetes manifest that glues them together
    K8S_YAML = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payment-service
spec:
  template:
    spec:
      containers:
        - name: app
          image: my-app:latest
          env:
            # Jnkan links this K8s env var to the Python code reading it
            - name: PAYMENT_DB_HOST
              valueFrom:
                secretKeyRef:
                  name: db-secrets
                  key: host
"""

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir

    def provision(self) -> Path:
        """
        Create the demo project structure on disk.

        Returns:
            Path: The path to the created demo directory.
        """
        demo_dir = self.root_dir / "jnkn-demo"
        demo_dir.mkdir(exist_ok=True)

        # 1. Create source directory
        src_dir = demo_dir / "src"
        src_dir.mkdir(exist_ok=True)
        (src_dir / "app.py").write_text(self.APP_PY.strip())

        # 2. Create terraform directory
        tf_dir = demo_dir / "terraform"
        tf_dir.mkdir(exist_ok=True)
        (tf_dir / "main.tf").write_text(self.INFRA_TF.strip())

        # 3. Create kubernetes directory
        k8s_dir = demo_dir / "k8s"
        k8s_dir.mkdir(exist_ok=True)
        (k8s_dir / "deployment.yaml").write_text(self.K8S_YAML.strip())

        return demo_dir