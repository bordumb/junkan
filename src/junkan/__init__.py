"""
Jnkn - The Pre-Flight Impact Analysis Engine.

Jnkn prevents production outages by stitching together the hidden
dependencies between Infrastructure (Terraform), Data Pipelines (dbt),
and Application Code.

Key Components:
- parsing: Multi-language code parsing (Python, JS, Terraform, K8s, dbt)
- core: Data types and graph structures
- stitching: Cross-domain dependency matching
- analysis: Impact and blast radius analysis

Usage:
    from jnkn.parsing import create_default_engine
    
    engine = create_default_engine()
    nodes, edges, stats = engine.scan_all()
"""

__version__ = "0.1.0"

from .core.types import (
    Node, Edge, NodeType, RelationshipType,
    MatchStrategy, MatchResult, ScanMetadata,
)

__all__ = [
    "__version__",
    "Node",
    "Edge",
    "NodeType",
    "RelationshipType",
    "MatchStrategy",
    "MatchResult",
    "ScanMetadata",
]