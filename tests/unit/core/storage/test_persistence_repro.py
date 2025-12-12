"""
Reproduction test for Metadata Persistence issues.
Verifies that nodes with arbitrary/custom metadata are correctly preserved
through the SQLite storage round-trip.
"""

from jnkn.core.types import Node, NodeType
from jnkn.core.storage.sqlite import SQLiteStorage

def test_persistence_integrity(tmp_path):
    """
    Simulate the exact lifecycle of a node from Parsing -> Storage -> Loading.
    """
    db_path = tmp_path / "repro.db"
    storage = SQLiteStorage(db_path)
    
    # 1. Simulate a Node created by the Python Parser
    # Note: 'source_pattern' might be a key that isn't in your TypedDict yet
    original_node = Node(
        id="env:PAYMENT_DB_HOST",
        name="PAYMENT_DB_HOST",
        type=NodeType.ENV_VAR,
        metadata={
            "source": "os.getenv",
            "file": "src/app.py",
            "line": 10,
            "random_parser_flag": "true",  # Test robust extra field handling
            "confidence": 0.95
        }
    )
    
    # 2. Save to DB
    print(f"\n[1] Saving Node: {original_node.id} with keys: {list(original_node.metadata.keys())}")
    storage.save_node(original_node)
    
    # 3. Clear memory (force DB reload)
    del original_node
    
    # 4. Load from DB
    loaded_node = storage.load_node("env:PAYMENT_DB_HOST")
    
    # 5. Verify
    assert loaded_node is not None, "❌ Node was not found in DB after saving!"
    
    print(f"[2] Loaded Node: {loaded_node.id}")
    print(f"[3] Metadata: {loaded_node.metadata}")
    
    # Check critical fields
    assert loaded_node.metadata.get("source") == "os.getenv", "❌ 'source' field missing or corrupted"
    
    # Check arbitrary fields (Crucial for the 'Artifact not found' issue)
    # If the TypedDict definition is too strict, this often fails or strips the data
    assert loaded_node.metadata.get("random_parser_flag") == "true", \
        "❌ Arbitrary metadata was stripped during persistence!"

    print("✅ Persistence test passed!")