"""
Dataset Extractor for OpenLineage.

This module handles the extraction of Input and Output datasets from OpenLineage events.
It creates nodes for the data assets (tables, files, topics) and establishes the
read/write relationships with the Job.
"""

import json
import re
from typing import Any, Dict, Generator, List, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class DatasetExtractor:
    """
    Extract Input/Output Datasets and link them to Jobs.

    This extractor processes the `inputs` and `outputs` arrays in an OpenLineage event.
    It creates DATA_ASSET nodes and connects them to the JOB node via READS/WRITES edges.
    """

    name = "openlineage_datasets"
    priority = 90

    def can_extract(self, ctx: ExtractionContext) -> bool:
        """
        Check if the text contains dataset definitions.

        Args:
            ctx: The extraction context.

        Returns:
            bool: True if 'inputs' or 'outputs' keys are present.
        """
        return '"inputs"' in ctx.text or '"outputs"' in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """
        Extract Dataset nodes and edges.

        Args:
            ctx: The extraction context.

        Yields:
            Union[Node, Edge]: Dataset nodes and READS/WRITES edges.
        """
        try:
            data = json.loads(ctx.text)
        except json.JSONDecodeError:
            return

        events = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

        for event in events:
            if event.get("eventType") not in ("COMPLETE", "RUNNING"):
                continue

            job = event.get("job", {})
            job_ns = job.get("namespace", "default")
            job_name = job.get("name")

            if not job_name:
                continue

            job_id = f"job:{job_ns}/{job_name}"

            # Process Inputs
            for ds in event.get("inputs", []):
                yield from self._process_dataset(ds, job_id, "input", ctx)

            # Process Outputs
            for ds in event.get("outputs", []):
                yield from self._process_dataset(ds, job_id, "output", ctx)

    def _process_dataset(
        self, dataset: Dict[str, Any], job_id: str, direction: str, ctx: ExtractionContext
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Helper to process a single dataset dictionary.

        Args:
            dataset: The dataset dictionary from the JSON.
            job_id: The ID of the job related to this dataset.
            direction: 'input' or 'output'.
            ctx: The extraction context.
        """
        namespace = dataset.get("namespace", "default")
        name = dataset.get("name")

        if not name:
            return

        dataset_id = f"data:{namespace}/{name}"

        # Create Node if not seen in this context
        if dataset_id not in ctx.seen_ids:
            ctx.seen_ids.add(dataset_id)

            # Extract schema fields for metadata
            facets = dataset.get("facets", {})
            schema_fields = []
            if "schema" in facets:
                schema_fields = [f.get("name") for f in facets["schema"].get("fields", [])]

            yield Node(
                id=dataset_id,
                name=name,
                type=NodeType.DATA_ASSET,
                tokens=self._tokenize(name),
                metadata={
                    "namespace": namespace,
                    "source": "openlineage",
                    "schema_fields": schema_fields,
                    "facets": facets,
                },
            )

        # Create Edge
        # Input: Job READS Dataset
        # Output: Job WRITES Dataset
        if direction == "input":
            yield Edge(
                source_id=job_id,
                target_id=dataset_id,
                type=RelationshipType.READS,
                confidence=1.0,  # Observed runtime data is high confidence
                metadata={"source": "openlineage"},
            )
        else:
            yield Edge(
                source_id=job_id,
                target_id=dataset_id,
                type=RelationshipType.WRITES,
                confidence=1.0,
                metadata={"source": "openlineage"},
            )

    def _tokenize(self, name: str) -> List[str]:
        """Tokenize dataset name."""
        return [t for t in re.split(r"[_\-./]", name.lower()) if len(t) >= 2]
