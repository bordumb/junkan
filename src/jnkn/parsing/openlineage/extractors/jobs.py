"""
Job Extractor for OpenLineage.

This module handles the extraction of 'Job' entities from OpenLineage events.
Jobs represent the processing units in the data lineage graph (e.g., a Spark application,
an Airflow task, or a dbt model run).
"""

import json
import re
from typing import Generator, List, Union

from ....core.types import Edge, Node, NodeType
from ...base import ExtractionContext


class JobExtractor:
    """
    Extract Job definitions from OpenLineage events.

    This extractor identifies the main subject of the event (the Job)
    and creates a corresponding Node in the graph. It also links the Job
    to the source file containing the event.
    """

    name = "openlineage_jobs"
    priority = 100

    def can_extract(self, ctx: ExtractionContext) -> bool:
        """
        Check if the text contains job definitions.

        Args:
            ctx: The extraction context.

        Returns:
            bool: True if 'job' and 'namespace' keys are present.
        """
        return '"job"' in ctx.text and '"namespace"' in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """
        Extract Job nodes from the JSON content.

        Args:
            ctx: The extraction context containing the JSON text.

        Yields:
            Union[Node, Edge]: The Job node and a 'contains' edge from the file.
        """
        try:
            data = json.loads(ctx.text)
        except json.JSONDecodeError:
            return

        # Normalize data to a list of events
        events = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

        for event in events:
            # Only process relevant event types.
            # We skip START/FAIL usually, but sometimes RUNNING has useful info.
            if event.get("eventType") not in ("COMPLETE", "RUNNING"):
                continue

            job = event.get("job", {})
            namespace = job.get("namespace", "default")
            name = job.get("name")

            if not name:
                continue

            # Unique ID for the job
            job_id = f"job:{namespace}/{name}"

            # Deduplication within the same file context
            if job_id in ctx.seen_ids:
                continue
            ctx.seen_ids.add(job_id)

            # Create the Job Node
            yield Node(
                id=job_id,
                name=name,
                type=NodeType.JOB,
                path=str(ctx.file_path),
                tokens=self._tokenize(name),
                metadata={
                    "namespace": namespace,
                    "source": "openlineage",
                    "facets": job.get("facets", {}),
                    "run_id": event.get("run", {}).get("runId"),
                    "event_time": event.get("eventTime"),
                },
            )

            # Link file to job (File CONTAINS Job)
            yield Edge(
                source_id=ctx.file_id,
                target_id=job_id,
                type="contains",  # Using string literal or RelationshipType.CONTAINS
            )

    def _tokenize(self, name: str) -> List[str]:
        """
        Tokenize the job name for fuzzy matching.

        Args:
            name: The job name.

        Returns:
            List[str]: List of tokens.
        """
        return [t for t in re.split(r"[_\-./]", name.lower()) if len(t) >= 2]
