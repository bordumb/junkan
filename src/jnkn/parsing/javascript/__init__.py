"""
JavaScript/TypeScript parsing module for jnkn.

Provides parsing for JavaScript and TypeScript files.
"""

from .parser import (
    JavaScriptParser,
    create_javascript_parser,
)

__all__ = [
    "JavaScriptParser",
    "create_javascript_parser",
]
