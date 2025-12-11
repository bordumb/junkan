"""
Integration Test: JSON Contract Enforcement.

Ensures that all CLI commands support the --json flag and return
the StandardResponse envelope structure defined in jnkn.core.api.envelope.
"""

import json
from typing import Any

import pytest
from click.testing import CliRunner

from jnkn.cli.main import main
from jnkn.core.api.envelope import StandardResponse

# UPDATED: 'blast' is the command name alias in main.py, not 'blast-radius'
COMMANDS_TO_TEST = [
    ["blast", "env:TEST_VAR", "--json"], 
    ["scan", ".", "--json", "--no-recursive"],
    ["check", "--json"]  # Might fail input validation, but must return JSON error
]

@pytest.mark.parametrize("args", COMMANDS_TO_TEST)
def test_command_json_contract(args):
    """
    Verify that commands return valid JSON envelopes.
    Even if the command fails (e.g. missing graph), the output
    must be parseable JSON adhering to the StandardResponse schema.
    """
    runner = CliRunner()
    result = runner.invoke(main, args)

    # 1. Output must be valid JSON
    try:
        data = json.loads(result.output)
    except json.JSONDecodeError:
        pytest.fail(f"Command {' '.join(args)} did not return valid JSON.\nOutput: {result.output}")

    # 2. Must adhere to StandardResponse schema
    # Pydantic validation handles checking meta, status, data/error fields
    try:
        # We use a generic 'Any' because data varies by command
        StandardResponse[Any].model_validate(data)
    except Exception as e:
        pytest.fail(f"JSON output does not match StandardResponse contract: {e}")

    # 3. Meta block checks
    assert "meta" in data
    assert "spec_version" in data["meta"]
    assert data["meta"]["spec_version"] == "1.0"
    assert "duration_ms" in data["meta"]

    # 4. Status checks
    assert data["status"] in ["success", "error", "partial"]

    # 5. Data vs Error mutual exclusivity (mostly)
    if data["status"] == "success":
        assert data["data"] is not None
        assert data["error"] is None
    elif data["status"] == "error":
        assert data["error"] is not None