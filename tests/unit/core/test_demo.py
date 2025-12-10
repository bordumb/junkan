"""
Unit tests for the Demo Manager.
"""

from pathlib import Path
from jnkn.core.demo import DemoManager

class TestDemoManager:
    """Test the demo environment provisioning."""

    def test_provision_creates_files(self, tmp_path):
        """Verify the directory structure and file contents are created."""
        manager = DemoManager(tmp_path)
        demo_dir = manager.provision()

        # Check directories
        assert demo_dir.exists()
        assert (demo_dir / "src").exists()
        assert (demo_dir / "terraform").exists()
        assert (demo_dir / "k8s").exists()

        # Check files
        app_py = demo_dir / "src/app.py"
        main_tf = demo_dir / "terraform/main.tf"
        k8s_yaml = demo_dir / "k8s/deployment.yaml"

        assert app_py.exists()
        assert main_tf.exists()
        assert k8s_yaml.exists()

        # Verify content integrity (key tokens must exist for stitching)
        assert 'os.getenv("PAYMENT_DB_HOST")' in app_py.read_text()
        assert 'output "payment_db_host"' in main_tf.read_text()
        assert 'name: PAYMENT_DB_HOST' in k8s_yaml.read_text()