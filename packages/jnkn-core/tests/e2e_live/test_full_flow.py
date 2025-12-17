"""
End-to-End Test for Epic 1.0: First Scan Must Wow.

This test validates the full user journey:
1. init --demo
2. scan (Discovery Mode)
3. scan (Enforcement Mode transition)
4. pack detection
5. multi-repo initialization (Phase 1)
"""

import shutil
import subprocess
import os
from pathlib import Path
import pytest
import time

# Helper to run jnkn commands
def run_jnkn(args, cwd, input_str=None):
    """Run a jnkn command in a subprocess."""
    cmd = ["jnkn"] + args
    result = subprocess.run(
        cmd,
        cwd=cwd,
        input=input_str,
        text=True,
        capture_output=True,
        env={**os.environ, "COLUMNS": "120"}  # Force width for rich output
    )
    return result

@pytest.fixture
def clean_workdir(tmp_path):
    """Create a clean working directory."""
    workdir = tmp_path / "e2e_workspace"
    workdir.mkdir()
    return workdir

def test_demo_flow_and_mode_transition(clean_workdir):
    """
    Scenario: New user runs demo, scans, and transitions to enforcement.
    """
    # 1. Initialize Demo
    # We pass 'y' for the telemetry prompt just in case
    init_res = run_jnkn(["init", "--demo"], cwd=clean_workdir, input_str="y\n")
    if init_res.returncode != 0:
        print(f"Init stdout: {init_res.stdout}")
        print(f"Init stderr: {init_res.stderr}")
    assert init_res.returncode == 0
    assert "Created demo project" in init_res.stdout
    
    demo_dir = clean_workdir / "jnkn-demo"
    assert demo_dir.exists()

    # 2. First Scan (Discovery)
    scan_res = run_jnkn(["scan"], cwd=demo_dir)
    assert scan_res.returncode == 0
    assert "Mode: Discovery" in scan_res.stdout
    assert "YOUR ARCHITECTURE AT A GLANCE" in scan_res.stdout
    assert "Cross-Domain Connections" in scan_res.stdout

    # 3. Explicit Mode Switch (Simulating post-review state)
    scan_enforce = run_jnkn(["scan", "--mode", "enforcement"], cwd=demo_dir)
    assert scan_enforce.returncode == 0
    assert "Mode: Enforcement" in scan_enforce.stdout

def test_multirepo_demo_init(clean_workdir):
    """
    Scenario: User initializes the new multi-repo demo (Phase 1).
    """
    # 1. Initialize Multi-Repo Demo
    init_res = run_jnkn(["init", "--demo", "--multirepo"], cwd=clean_workdir, input_str="y\n")
    
    if init_res.returncode != 0:
        print(f"Init stdout: {init_res.stdout}")
        print(f"Init stderr: {init_res.stderr}")
    assert init_res.returncode == 0
    assert "Multi-repo demo created" in init_res.stdout
    
    # Check structure
    app_dir = clean_workdir / "jnkn-demo" / "payment-service"
    infra_dir = clean_workdir / "jnkn-demo" / "infrastructure"
    
    assert app_dir.exists()
    assert infra_dir.exists()
    assert (app_dir / "jnkn.toml").exists()
    
    # 2. Run Scan from App Dir (should resolve infra dependency)
    scan_res = run_jnkn(["scan"], cwd=app_dir)
    
    if scan_res.returncode != 0:
        print(f"Scan stdout: {scan_res.stdout}")
        print(f"Scan stderr: {scan_res.stderr}")
        
    assert scan_res.returncode == 0
    # Output should indicate parsing files in the dependency
    assert "Parsed" in scan_res.stdout
    assert "infrastructure" in scan_res.stdout # We logged repo names in scan command

def test_framework_pack_detection(clean_workdir):
    """
    Scenario: User initializes a Django project and accepts the pack.
    """
    project_dir = clean_workdir / "my_django_app"
    project_dir.mkdir()
    
    # Create Django indicators
    (project_dir / "requirements.txt").write_text("django==4.2.0")
    (project_dir / "manage.py").touch()
    
    # Create Terraform indicators
    (project_dir / "infra").mkdir()
    (project_dir / "infra/main.tf").touch()

    # Run Init and accept the pack (input="y")
    init_res = run_jnkn(["init"], cwd=project_dir, input_str="y\ny\n") 
    
    assert init_res.returncode == 0
    assert "Detected project type: django-aws" in init_res.stdout
    assert "Pack enabled: django-aws" in init_res.stdout
    
    # Verify config file
    config_path = project_dir / ".jnkn/config.yaml"
    assert config_path.exists()
    assert "pack: django-aws" in config_path.read_text()

def test_json_output_contract(clean_workdir):
    """
    Scenario: CI pipeline requests JSON output.
    """
    # Create a minimal valid project
    (clean_workdir / "app.py").write_text("import os\nX = os.getenv('Y')")
    
    # Init (non-interactive force)
    run_jnkn(["init", "--force", "--no-telemetry"], cwd=clean_workdir)
    
    # Scan with JSON
    res = run_jnkn(["scan", "--json"], cwd=clean_workdir)
    assert res.returncode == 0
    
    # Check output is valid JSON
    import json
    data = json.loads(res.stdout)
    assert data["status"] == "success"
    # Ensure data payload exists
    assert "data" in data
    assert "nodes_found" in data["data"]