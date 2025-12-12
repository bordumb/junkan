"""
OpenLineage Parsing Module.

This module provides the integration for parsing OpenLineage event files (JSON).
It enriches the static dependency graph with runtime observations, allowing
users to stitch code definitions (like Spark jobs) to the actual datasets
they produce and consume in production.

Exposes:
    - OpenLineageParser: The main parser class.
    - create_openlineage_parser: Factory function for engine registration.
    - fetch_from_marquez: Utility to pull events from a Marquez API.
"""

from .parser import OpenLineageParser, create_openlineage_parser, fetch_from_marquez

__all__ = ["OpenLineageParser", "create_openlineage_parser", "fetch_from_marquez"]
