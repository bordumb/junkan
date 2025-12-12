"""
Column Extractor for OpenLineage.

This module handles the extraction of Column entities and column-level lineage
from OpenLineage event facets. It allows for fine-grained dependency tracking
down to the field level.
"""

import json
import re
from typing import Generator, List, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class ColumnExtractor:
    """
    Extract Column definitions and Column-level lineage from facets.

    This extractor looks for the `schema` facet to identify columns and the
    `columnLineage` facet to identify transformations between input and output columns.
    """

    name = "openlineage_columns"
    priority = 80

    def can_extract(self, ctx: ExtractionContext) -> bool:
        """
        Check if the text contains schema or column lineage information.

        Args:
            ctx: The extraction context.

        Returns:
            bool: True if 'schema' or 'columnLineage' keys are present.
        """
        return '"schema"' in ctx.text or '"columnLineage"' in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """
        Extract Column nodes and Transformation edges.

        Args:
            ctx: The extraction context.

        Yields:
            Union[Node, Edge]: Column nodes, CONTAINS edges (Dataset->Column), and TRANSFORMS edges.
        """
        try:
            data = json.loads(ctx.text)
        except json.JSONDecodeError:
            return

        events = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

        for event in events:
            # We typically only get schema/lineage on COMPLETE events
            if event.get("eventType") != "COMPLETE":
                continue

            # Check both inputs and outputs for schema info
            all_datasets = event.get("inputs", []) + event.get("outputs", [])

            for ds in all_datasets:
                namespace = ds.get("namespace", "default")
                name = ds.get("name")
                facets = ds.get("facets", {})

                if not name:
                    continue

                # 1. Extract Columns from Schema Facet
                schema = facets.get("schema", {})
                if schema and "fields" in schema:
                    for field_info in schema["fields"]:
                        col_name = field_info.get("name")
                        if not col_name:
                            continue

                        col_id = f"column:{namespace}/{name}/{col_name}"

                        if col_id not in ctx.seen_ids:
                            ctx.seen_ids.add(col_id)
                            yield Node(
                                id=col_id,
                                name=col_name,
                                type=NodeType.DATA_ASSET,
                                tokens=self._tokenize(col_name),
                                metadata={
                                    "namespace": namespace,
                                    "table": name,
                                    "data_type": field_info.get("type"),
                                    "source": "openlineage",
                                    "is_column": True,
                                },
                            )
                            # Link Dataset -> Column (Contains)
                            # Note: We rely on DatasetExtractor having run to create the parent dataset node
                            yield Edge(
                                source_id=f"data:{namespace}/{name}",
                                target_id=col_id,
                                type=RelationshipType.CONTAINS,
                            )

                # 2. Extract Lineage from ColumnLineage Facet
                # This maps Output Column <- Input Columns
                col_lineage = facets.get("columnLineage", {})
                if col_lineage and "fields" in col_lineage:
                    for tgt_col, lineage_info in col_lineage["fields"].items():
                        tgt_id = f"column:{namespace}/{name}/{tgt_col}"

                        for input_field in lineage_info.get("inputFields", []):
                            src_ns = input_field.get("namespace", namespace)
                            src_name = input_field.get("name", name)
                            src_col = input_field.get("field")

                            if src_col:
                                src_id = f"column:{src_ns}/{src_name}/{src_col}"

                                yield Edge(
                                    source_id=src_id,
                                    target_id=tgt_id,
                                    type=RelationshipType.TRANSFORMS,
                                    confidence=1.0,
                                    metadata={
                                        "source": "openlineage",
                                        "transformations": input_field.get("transformations", []),
                                    },
                                )

    def _tokenize(self, name: str) -> List[str]:
        """Tokenize column name."""
        return [t for t in re.split(r"[_\-./]", name.lower()) if len(t) >= 2]
