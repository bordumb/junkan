"""
Unit tests for CLI formatting utilities.
"""

import click
import pytest
from jnkn.cli.formatting import _get_domain, format_blast_radius

class TestFormatting:
    """Tests for the output formatter."""

    def test_domain_detection(self):
        """Verify artifacts are mapped to correct domains."""
        # Config
        assert _get_domain("env:DB_URL") == "config"
        
        # Infra
        assert _get_domain("infra:aws_s3_bucket.main") == "terraform"
        
        # Kubernetes
        assert _get_domain("k8s:default/deployment/api") == "kubernetes"
        assert _get_domain("file://k8s/deploy.yaml") == "kubernetes"
        
        # Code
        assert _get_domain("file://src/main.py") == "python"
        assert _get_domain("file://src/app.ts") == "javascript"
        assert _get_domain("file://src/index.js") == "javascript"
        
        # Data
        assert _get_domain("data:warehouse.users") == "data"
        
        # Fallback
        assert _get_domain("unknown:artifact") == "other"
        assert _get_domain("file://README.md") == "other"

    def test_format_blast_radius_output(self):
        """Verify the full text report structure."""
        result = {
            "source_artifacts": ["env:DATABASE_URL"],
            "impacted_artifacts": [
                "file://src/api.py",
                "file://src/db.py",
                "infra:aws_db_instance.main",
                "k8s:deploy/api",
                "unknown:thing"
            ]
        }
        
        output = format_blast_radius(result)
        # IMPORTANT: Strip ANSI color codes for robust assertion
        clean = click.unstyle(output)
        
        # Check Headers
        assert "💥 Blast Radius Analysis" in clean
        assert "Source: env:DATABASE_URL" in clean
        
        # Check Groups
        assert "🐍  Python Code (2)" in clean
        assert "🏗️  Terraform (1)" in clean
        assert "☸️  Kubernetes (1)" in clean
        assert "📦  Other Artifacts (1)" in clean
        
        # Check Items
        assert "• src/api.py" in clean
        assert "• aws_db_instance.main" in clean
        assert "• unknown:thing" in clean

    def test_format_empty_results(self):
        """Verify handling of no impact."""
        result = {
            "source_artifacts": ["env:UNUSED"],
            "impacted_artifacts": []
        }
        
        output = format_blast_radius(result)
        clean = click.unstyle(output)
        
        assert "No downstream dependencies found" in clean