"""
dbt parsing module for Jnkn.

Provides parsing for dbt manifest.json files to extract:
- Models, sources, seeds, snapshots
- ref() and source() dependencies
- Column definitions and lineage
- Exposures (downstream consumers)

Usage:
    from jnkn.parsing.dbt import DbtManifestParser
    
    parser = DbtManifestParser()
    result = parser.parse_full(Path("target/manifest.json"))
    
    # Or use convenience methods
    lineage = parser.extract_lineage(manifest_path)
    nodes = parser.extract_nodes_list(manifest_path)
"""

from .manifest_parser import (
    DbtManifestParser,
    DbtNode,
    DbtColumn,
    DbtExposure,
    create_dbt_manifest_parser,
)

__all__ = [
    "DbtManifestParser",
    "DbtNode",
    "DbtColumn",
    "DbtExposure",
    "create_dbt_manifest_parser",
]
