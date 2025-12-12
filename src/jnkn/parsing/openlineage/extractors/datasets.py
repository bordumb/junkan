import json
import re
from typing import Any, Dict, Generator, List, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class DatasetExtractor:
    """Extract Input/Output Datasets and link them to Jobs."""

    name = "openlineage_datasets"
    priority = 90

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return '"inputs"' in ctx.text or '"outputs"' in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        try:
            data = json.loads(ctx.text)
        except json.JSONDecodeError:
            return

        events = data if isinstance(data, list) else [data] if isinstance(data, dict) else []

        for event in events:
            if event.get("eventType") not in ("COMPLETE", "RUNNING"):
                continue

            job = event.get("job", {})
            job_id = f"job:{job.get('namespace', 'default')}/{job.get('name')}"

            # Process Inputs
            for ds in event.get("inputs", []):
                yield from self._process_dataset(ds, job_id, "input", ctx)

            # Process Outputs
            for ds in event.get("outputs", []):
                yield from self._process_dataset(ds, job_id, "output", ctx)

    def _process_dataset(
        self, dataset: Dict[str, Any], job_id: str, direction: str, ctx: ExtractionContext
    ) -> Generator[Union[Node, Edge], None, None]:
        namespace = dataset.get("namespace", "default")
        name = dataset.get("name")

        if not name:
            return

        dataset_id = f"data:{namespace}/{name}"

        # Create Node if not seen
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
                confidence=1.0,
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
        return [t for t in re.split(r"[_\-./]", name.lower()) if len(t) >= 2]
