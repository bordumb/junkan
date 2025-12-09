"""
Analysis modules for Jnkn.

This package contains analysis and explanation capabilities:
- explain: Match explanation generator
"""

from .explain import (
    ExplanationGenerator, MatchExplanation, NodeInfo, AlternativeMatch,
    create_explanation_generator
)

__all__ = [
    "ExplanationGenerator", "MatchExplanation", "NodeInfo", "AlternativeMatch",
    "create_explanation_generator",
]