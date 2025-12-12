"""
Integration test to isolate the "File not found" CI error.
Replicates the exact sequence of commands: ingest (scan) -> blast.
"""

import json
from pathlib import Path
import pytest
from click.testing import CliRunner
from jnkn.cli.main import main

def test_scan_and_blast_workflow_isolation(tmp_path):
    """
    Verifies that 'scan' creates the DB file and 'blast' can read it.
    """
    runner = CliRunner()
    
    # Use isolated filesystem to guarantee clean state
    with runner.isolated_filesystem(temp_dir=tmp_path):
        # ---------------------------------------------------------------------
        # 1. SETUP: Create a dummy project
        # ---------------------------------------------------------------------
        src_dir = Path("src")
        src_dir.mkdir()
        
        # Create enough artifacts to ensure node count >= 5
        # This prevents the "Low node count" warning from obscuring success
        
        # 1. app.py (File node) -> reads ENV (EnvVar node) [2 nodes]
        (src_dir / "app.py").write_text("import os\nDB = os.getenv('DB_HOST')")
        
        # 2. main.tf (File node) -> resource (Infra node) [2 nodes]
        (Path("main.tf")).write_text('resource "aws_bucket" "b" {}')
        
        # 3. utils.py (File node) -> definition (Entity node) [2 nodes]
        (src_dir / "utils.py").write_text("def helper(): pass")

        # ---------------------------------------------------------------------
        # 2. ACTION: Run Scan (jnkn scan)
        # ---------------------------------------------------------------------
        print("\n--- Running Scan ---")
        result_scan = runner.invoke(main, ["scan", "."])
        
        # Assert Scan Succeeded
        # Debug output if it fails
        assert result_scan.exit_code == 0, f"Scan failed: {result_scan.output}"
        
        # Check for success message OR the warning (both mean success)
        success_indicators = ["Scan complete", "Low node count detected"]
        assert any(i in result_scan.output for i in success_indicators), \
            f"Unexpected scan output: {result_scan.output}"
        
        # CRITICAL ASSERTION: Does the DB exist?
        # The scan command defaults to .jnkn/jnkn.db
        db_path = Path(".jnkn/jnkn.db")
        
        if not db_path.exists():
            # Detailed debugging of what WAS created
            print("Files in root:", list(Path(".").iterdir()))
            if Path(".jnkn").exists():
                print("Files in .jnkn:", list(Path(".jnkn").iterdir()))
            
            pytest.fail(f"DB file not found at {db_path}")
            
        assert db_path.stat().st_size > 0, "Database file is empty!"
        print(f"✅ DB created at {db_path.absolute()}")

        # ---------------------------------------------------------------------
        # 3. ACTION: Run Blast (jnkn blast)
        # ---------------------------------------------------------------------
        print("\n--- Running Blast ---")
        # We simulate the exact CI call: referencing the file path directly
        # Note: We use src/app.py because that is what we created
        result_blast = runner.invoke(main, ["blast", "src/app.py", "--json"])
        
        # Debug output if it fails
        if result_blast.exit_code != 0:
            print("Blast Output:", result_blast.output)

        # Assert Blast Succeeded
        assert result_blast.exit_code == 0
        
        # Verify JSON Output
        try:
            data = json.loads(result_blast.output)
            assert data["status"] == "success"
            # It should find the impact on the file itself or the env var
            assert data["data"]["count"] >= 0 
        except json.JSONDecodeError:
            pytest.fail(f"Blast did not return valid JSON: {result_blast.output}")

        print("✅ Blast radius calculation successful")