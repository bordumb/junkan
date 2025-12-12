"""
JavaScript/TypeScript Extractors.

Exports the list of all available extractors for the JavaScript parser.
"""

from .definitions import DefinitionExtractor
from .env_vars import EnvVarExtractor
from .imports import ImportExtractor
from .nextjs import NextJSExtractor
from .package_json import PackageJsonExtractor

# Registry list used by the parser
JAVASCRIPT_EXTRACTORS = [
    EnvVarExtractor(),  # Priority 100
    ImportExtractor(),  # Priority 90
    DefinitionExtractor(),  # Priority 80
    NextJSExtractor(),  # Priority 70
    PackageJsonExtractor(),  # Priority 40
]

__all__ = [
    "JAVASCRIPT_EXTRACTORS",
    "EnvVarExtractor",
    "ImportExtractor",
    "DefinitionExtractor",
    "NextJSExtractor",
    "PackageJsonExtractor",
]
