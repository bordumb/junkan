"""
Tests to verify fix for Blast Radius and Trace failures in CLI.
"""

import pytest
from click.testing import CliRunner
from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.core.storage.sqlite import SQLiteStorage
from jnkn.cli.commands.blast_radius import blast_radius
from jnkn.cli.commands.trace import trace

@pytest.fixture
def populated_db(tmp_path):
    """
    Creates a temporary SQLite DB populated with the Demo Graph structure.
    """
    db_path = tmp_path / "jnkn.db"
    storage = SQLiteStorage(db_path)
    
    nodes = [
        Node(id="infra:output:payment_db_host", name="payment_db_host", type=NodeType.CONFIG_KEY),
        Node(id="env:PAYMENT_DB_HOST", name="PAYMENT_DB_HOST", type=NodeType.ENV_VAR),
        Node(id="file://src/app.py", name="app.py", type=NodeType.CODE_FILE)
    ]
    
    edges = [
        # Infra provides the Env Var
        Edge(
            source_id="infra:output:payment_db_host", 
            target_id="env:PAYMENT_DB_HOST", 
            type=RelationshipType.PROVIDES
        ),
        # App reads the Env Var (Reverse dependency)
        Edge(
            source_id="file://src/app.py", 
            target_id="env:PAYMENT_DB_HOST", 
            type=RelationshipType.READS
        )
    ]
    
    storage.save_nodes_batch(nodes)
    storage.save_edges_batch(edges)
    storage.close()
    return str(db_path)

def test_blast_radius_reverse_impact(populated_db):
    """
    Verifies that blast radius correctly identifies upstream readers.
    Changing the Env Var should impact the App File.
    """
    runner = CliRunner()
    result = runner.invoke(blast_radius, ["env:PAYMENT_DB_HOST", "--db", populated_db])
    
    assert result.exit_code == 0
    
    # The formatted output strips 'file://', so we check for the path
    # Expected output: "• src/app.py"
    assert "src/app.py" in result.output
    assert "Blast Radius Analysis" in result.output

def test_trace_with_terraform_heuristic(populated_db):
    """
    Verifies that 'infra:payment_db_host' resolves to 'infra:output:payment_db_host'.
    Also verifies the trace works (conceptually tracing line of impact).
    """
    runner = CliRunner()
    # User types 'infra:payment_db_host', but node is 'infra:output:payment_db_host'
    # Target is 'file://src/app.py'
    
    # Note: Dependency is Infra -> Env <- App (App reads Env)
    # The new trace command logic allows visualizing "Consumer -> Provider" paths via reverse trace.
    result = runner.invoke(trace, [
        "infra:payment_db_host", 
        "file://src/app.py", 
        "--graph", populated_db
    ])
    
    assert result.exit_code == 0
    # 1. Verify Node Resolution Worked
    assert "From: infra:output:payment_db_host" in result.output
    
    # 2. Verify Lineage/Impact Trace was found
    # Since direct dependency is broken (App reads Env), but lineage exists,
    # the command should output the found path.
    # If the unified graph handles semantics, it will find it.
    # With the new trace.py logic, it finds the reverse path and displays it.
    assert "path(s) found" in result.output