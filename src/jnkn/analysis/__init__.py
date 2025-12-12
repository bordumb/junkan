"""
Analysis modules for jnkn.

This package contains analysis and explanation capabilities:
- explain: Match explanation generator
"""

from .explain import (
    AlternativeMatch,
    ExplanationGenerator,
    MatchExplanation,
    NodeInfo,
    create_explanation_generator,
)

__all__ = [
    "ExplanationGenerator",
    "MatchExplanation",
    "NodeInfo",
    "AlternativeMatch",
    "create_explanation_generator",
]
