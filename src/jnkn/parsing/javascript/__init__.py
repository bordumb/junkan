"""
JavaScript/TypeScript parsing module for jnkn.

Provides parsing for JavaScript and TypeScript files:
- Environment variable detection (process.env, import.meta.env)
- Import statement extraction (ES modules, CommonJS)
- Function and class definition extraction
- Framework-specific patterns (Next.js, Vite, etc.)

Usage:
    from jnkn.parsing.javascript import JavaScriptParser
    
    parser = JavaScriptParser()
    result = parser.parse_full(Path("app.ts"))
"""

from .parser import (
    JavaScriptParser,
    JSEnvVar,
    JSImport,
    create_javascript_parser,
)

__all__ = [
    "JavaScriptParser",
    "JSEnvVar",
    "JSImport",
    "create_javascript_parser",
]