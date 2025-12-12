"""
OpenLineage Extractors.

This package contains specialized extractors for different components of
an OpenLineage event:
- Jobs: The executable units (Spark jobs, Airflow tasks).
- Datasets: The data inputs and outputs.
- Columns: The schema fields and their lineage.
"""

from .columns import ColumnExtractor
from .datasets import DatasetExtractor
from .jobs import JobExtractor

__all__ = [
    "JobExtractor",
    "DatasetExtractor",
    "ColumnExtractor",
]
