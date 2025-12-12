"""
Standardized OpenLineage Parser.

Parses OpenLineage JSON events to extract runtime lineage graph nodes.
Supports both single event objects and lists of events.
"""

from pathlib import Path
from typing import Any, Dict, Generator, List, Union

try:
    import requests

    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from ...core.types import Edge, Node, NodeType
from ..base import (
    ExtractionContext,
    ExtractorRegistry,
    LanguageParser,
    ParserCapability,
    ParserContext,
)
from .extractors.columns import ColumnExtractor
from .extractors.datasets import DatasetExtractor
from .extractors.jobs import JobExtractor


class OpenLineageParser(LanguageParser):
    """
    Parser for OpenLineage JSON files.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        """Register extractors in priority order."""
        # Jobs create the central nodes (Priority 100)
        self._extractors.register(JobExtractor())
        # Datasets connect to jobs (Priority 90)
        self._extractors.register(DatasetExtractor())
        # Columns connect to datasets (Priority 80)
        self._extractors.register(ColumnExtractor())

    @property
    def name(self) -> str:
        return "openlineage"

    @property
    def extensions(self) -> List[str]:
        return [".json"]

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.DATA_LINEAGE,
            ParserCapability.DEPENDENCIES,
        ]

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if file is an OpenLineage event.
        Looks for .json extension and specific keys in the content.
        """
        if file_path.suffix != ".json":
            return False

        # Heuristic check on content
        try:
            # Read first 1kb to check structure without loading full file
            with open(file_path, "r") as f:
                start = f.read(1024)
            return '"runId"' in start or '"eventType"' in start or '"openlineage"' in start
        except Exception:
            return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        # Decode content
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            return

        # Create file node
        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="json",
            metadata={"parser": "openlineage"},
        )

        # Create extraction context
        ctx = ExtractionContext(
            file_path=file_path,
            file_id=file_id,
            text=text,
            seen_ids=set(),
        )

        yield from self._extractors.extract_all(ctx)


def create_openlineage_parser(context: ParserContext | None = None) -> OpenLineageParser:
    """Factory function for OpenLineageParser."""
    return OpenLineageParser(context)


def fetch_from_marquez(
    base_url: str,
    namespace: str | None = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Helper to fetch events from Marquez API for ingestion.
    """
    if not HAS_REQUESTS:
        raise ImportError("requests library required. pip install requests")

    events = []
    jobs_url = (
        f"{base_url}/api/v1/namespaces/{namespace}/jobs"
        if namespace
        else f"{base_url}/api/v1/namespaces"
    )

    try:
        resp = requests.get(jobs_url, timeout=30)
        if not resp.ok:
            return []

        jobs_data = resp.json()

        # Flatten jobs list depending on API response structure
        jobs_list = jobs_data.get("jobs", []) if isinstance(jobs_data, dict) else []

        for job in jobs_list[:limit]:
            job_ns = job.get("namespace", namespace or "default")
            job_name = job.get("name")

            runs_url = f"{base_url}/api/v1/namespaces/{job_ns}/jobs/{job_name}/runs"
            runs_resp = requests.get(runs_url, timeout=30)

            if runs_resp.ok:
                runs_data = runs_resp.json()
                for run in runs_data.get("runs", [])[:5]:
                    if run.get("state") == "COMPLETED":
                        events.append(
                            {
                                "eventType": "COMPLETE",
                                "eventTime": run.get("endedAt"),
                                "job": {"namespace": job_ns, "name": job_name},
                                "inputs": [
                                    {"namespace": i.get("namespace"), "name": i.get("name")}
                                    for i in job.get("inputs", [])
                                ],
                                "outputs": [
                                    {"namespace": o.get("namespace"), "name": o.get("name")}
                                    for o in job.get("outputs", [])
                                ],
                                "run": {"runId": run.get("id")},
                            }
                        )
    except Exception:
        pass

    return events
