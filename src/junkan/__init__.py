"""
Junkan: The Pre-Flight Impact Analysis Engine

Junkan prevents production outages by stitching together the hidden
dependencies between Infrastructure (Terraform), Data Pipelines (dbt),
and Application Code.

Key Features:
- Multi-language parsing via tree-sitter
- Cross-domain dependency stitching (code <-> infra <-> data)
- Incremental scanning with file hash tracking
- Production-ready SQLite persistence with batching
- Configurable matching strategies with confidence scoring
"""

__version__ = "0.4.0"
__author__ = "Junkan Team"

from .core import (
    Node, Edge, NodeType, RelationshipType,
    DependencyGraph, ConfidenceCalculator
)

__all__ = [
    "__version__",
    "Node", "Edge", "NodeType", "RelationshipType",
    "DependencyGraph", "ConfidenceCalculator",
]