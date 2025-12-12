"""
OpenLineage parsing module for jnkn.

Provides parsing for OpenLineage event files (JSON) to extract:
- Jobs (Spark, Airflow, etc.)
- Datasets (Inputs/Outputs)
- Column-level lineage (via facets)
"""

from .parser import OpenLineageParser, create_openlineage_parser, fetch_from_marquez

__all__ = ["OpenLineageParser", "create_openlineage_parser", "fetch_from_marquez"]
