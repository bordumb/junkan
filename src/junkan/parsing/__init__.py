"""
Parsing module for Jnkn.

This module provides the extensible parsing framework that converts
source files into nodes and edges for the dependency graph.

Key Components:
- LanguageParser: Abstract base class for language-specific parsers
- ParserEngine: Central orchestrator for parsing operations
- ParserRegistry: Plugin-style parser registration

Supported Languages:
- Python (.py, .pyi)
- Terraform (.tf, .tf.json)
- JavaScript/TypeScript (.js, .ts, .jsx, .tsx)
- Kubernetes YAML (.yaml, .yml)
- dbt manifest.json

Usage:
    from jnkn.parsing import create_default_engine
    
    engine = create_default_engine()
    
    # Parse single file
    result = engine.parse_file_full(Path("app.py"))
    
    # Scan directory
    for result in engine.scan():
        print(f"Found {len(result.nodes)} nodes in {result.file_path}")
"""

from .base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
    ParseResult,
    ParseError,
    CompositeParser,
)

from .engine import (
    ParserEngine,
    ParserRegistry,
    ScanConfig,
    ScanStats,
    create_default_engine,
    DEFAULT_SKIP_DIRS,
    DEFAULT_SKIP_PATTERNS,
)

__all__ = [
    # Base classes
    "LanguageParser",
    "ParserCapability",
    "ParserContext",
    "ParseResult",
    "ParseError",
    "CompositeParser",
    # Engine
    "ParserEngine",
    "ParserRegistry",
    "ScanConfig",
    "ScanStats",
    "create_default_engine",
    # Constants
    "DEFAULT_SKIP_DIRS",
    "DEFAULT_SKIP_PATTERNS",
]