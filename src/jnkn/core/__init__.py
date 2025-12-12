"""
Core modules for jnkn.

This package contains the fundamental building blocks:
- types: Data structures (Node, Edge, etc.)
- graph: In-memory dependency graph
- confidence: Confidence calculation engine
"""

from .confidence import (
    ConfidenceCalculator,
    ConfidenceConfig,
    ConfidenceResult,
    ConfidenceSignal,
    PenaltyType,
    create_default_calculator,
)
from .graph import DependencyGraph, TokenIndex
from .types import Edge, MatchResult, MatchStrategy, Node, NodeType, RelationshipType, ScanMetadata

__all__ = [
    # Types
    "Node",
    "Edge",
    "NodeType",
    "RelationshipType",
    "MatchStrategy",
    "MatchResult",
    "ScanMetadata",
    # Graph
    "DependencyGraph",
    "TokenIndex",
    # Confidence
    "ConfidenceCalculator",
    "ConfidenceConfig",
    "ConfidenceResult",
    "ConfidenceSignal",
    "PenaltyType",
    "create_default_calculator",
]
