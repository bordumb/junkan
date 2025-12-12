"""
Standardized OpenLineage Parser.

This module implements the `LanguageParser` interface for OpenLineage JSON events.
It orchestrates a suite of specialized extractors to convert runtime lineage events
into graph nodes and edges.

Key Responsibilities:
    - Validating file content as OpenLineage JSON.
    - Coordinating job, dataset, and column extraction.
    - Providing a utility to fetch live lineage data from Marquez.
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

    This parser reads JSON files containing one or more OpenLineage events
    (e.g., `RunEvent`) and extracts a connectivity graph. It is designed to
    augment static analysis with high-confidence runtime data.

    Attributes:
        context (ParserContext): The shared parsing context.
        _extractors (ExtractorRegistry): The registry of configured extractors.
    """

    def __init__(self, context: ParserContext | None = None):
        """
        Initialize the OpenLineage parser.

        Args:
            context: The parser context containing root directory and settings.
                     If None, a default context is created.
        """
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        """
        Register the standard suite of OpenLineage extractors.

        Extractors are registered with specific priorities to ensure
        nodes are created in a logical order (Jobs -> Datasets -> Columns).
        """
        # Jobs create the central nodes (Priority 100)
        self._extractors.register(JobExtractor())
        # Datasets connect to jobs (Priority 90)
        self._extractors.register(DatasetExtractor())
        # Columns connect to datasets (Priority 80)
        self._extractors.register(ColumnExtractor())

    @property
    def name(self) -> str:
        """
        Get the unique name of this parser.

        Returns:
            str: "openlineage"
        """
        return "openlineage"

    @property
    def extensions(self) -> List[str]:
        """
        Get the list of supported file extensions.

        Returns:
            List[str]: [".json"]
        """
        return [".json"]

    def get_capabilities(self) -> List[ParserCapability]:
        """
        Get the list of capabilities provided by this parser.

        Returns:
            List[ParserCapability]: capabilities including DATA_LINEAGE and DEPENDENCIES.
        """
        return [
            ParserCapability.DATA_LINEAGE,
            ParserCapability.DEPENDENCIES,
        ]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        """
        Determine if the file contains OpenLineage data.

        This method uses a heuristic approach. Since `.json` is generic,
        it inspects the file content for OpenLineage-specific keys like
        `runId`, `eventType`, or `openlineage` schema URLs.

        Args:
            file_path: Path to the file.
            content: Optional bytes content of the file.

        Returns:
            bool: True if the file appears to be an OpenLineage event log.
        """
        if file_path.suffix != ".json":
            return False

        # If content is provided, check it directly
        if content:
            try:
                # Read start of file to check structure
                start = content[:1024].decode("utf-8", errors="ignore")
                return '"runId"' in start or '"eventType"' in start or '"openlineage"' in start
            except Exception:
                return False

        # If no content provided, try reading the file header
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                start = f.read(1024)
            return '"runId"' in start or '"eventType"' in start or '"openlineage"' in start
        except Exception:
            return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse the file and yield graph artifacts.

        Args:
            file_path: The path to the file being parsed.
            content: The raw bytes of the file.

        Yields:
            Union[Node, Edge]: Extracted nodes and edges.
        """
        # Decode content
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            # Fallback for non-utf8 files
            try:
                text = content.decode("latin-1")
            except Exception as e:
                self._logger.debug(f"Failed to decode {file_path}: {e}")
                return

        # Create a file node to represent the source of these events
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

        # Delegate to registered extractors
        yield from self._extractors.extract_all(ctx)


def create_openlineage_parser(context: ParserContext | None = None) -> OpenLineageParser:
    """
    Factory function to create an OpenLineageParser instance.

    Args:
        context: Optional parser context.

    Returns:
        OpenLineageParser: An initialized parser instance.
    """
    return OpenLineageParser(context)


def fetch_from_marquez(
    base_url: str,
    namespace: str | None = None,
    limit: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Fetch lineage events from a Marquez API.

    This utility connects to a running Marquez instance, retrieves jobs
    (optionally filtered by namespace), and fetches the latest COMPLETED run
    for each job. It formats the data as OpenLineage events suitable for parsing.

    Args:
        base_url: The base URL of the Marquez API (e.g., "http://localhost:5000").
        namespace: Optional namespace to filter jobs (e.g., "spark_prod").
        limit: The maximum number of jobs to fetch.

    Returns:
        List[Dict[str, Any]]: A list of OpenLineage event dictionaries.

    Raises:
        ImportError: If the 'requests' library is not installed.
    """
    if not HAS_REQUESTS:
        raise ImportError("requests library required. pip install requests")

    events = []

    # Construct URL based on whether namespace is provided
    if namespace:
        jobs_url = f"{base_url}/api/v1/namespaces/{namespace}/jobs"
    else:
        jobs_url = f"{base_url}/api/v1/namespaces"

    try:
        # Fetch jobs
        resp = requests.get(jobs_url, timeout=30)
        if not resp.ok:
            return []

        jobs_data = resp.json()

        # Normalize response structure (Marquez API structure varies by version)
        jobs_list = []
        if isinstance(jobs_data, dict):
            jobs_list = jobs_data.get("jobs", [])
        elif isinstance(jobs_data, list):
            jobs_list = jobs_data

        # Iterate through jobs and fetch runs
        for job in jobs_list[:limit]:
            job_ns = job.get("namespace", namespace or "default")
            job_name = job.get("name")

            if not job_name:
                continue

            runs_url = f"{base_url}/api/v1/namespaces/{job_ns}/jobs/{job_name}/runs"
            runs_resp = requests.get(runs_url, timeout=30)

            if runs_resp.ok:
                runs_data = runs_resp.json()
                runs = runs_data.get("runs", [])

                # We only care about the latest completed runs to get the current schema/lineage
                for run in runs[:5]:
                    if run.get("state") == "COMPLETED":
                        # Reconstruct an OpenLineage-like event structure
                        events.append(
                            {
                                "eventType": "COMPLETE",
                                "eventTime": run.get("endedAt"),
                                "job": {
                                    "namespace": job_ns,
                                    "name": job_name,
                                    "facets": job.get("facets", {}),
                                },
                                "inputs": [
                                    {
                                        "namespace": i.get("namespace"),
                                        "name": i.get("name"),
                                        "facets": i.get("facets", {}),
                                    }
                                    for i in job.get("inputs", [])
                                ],
                                "outputs": [
                                    {
                                        "namespace": o.get("namespace"),
                                        "name": o.get("name"),
                                        "facets": o.get("facets", {}),
                                    }
                                    for o in job.get("outputs", [])
                                ],
                                "run": {"runId": run.get("id"), "facets": run.get("facets", {})},
                            }
                        )
    except Exception:
        # Silently fail on network errors to avoid crashing the whole ingestion process
        pass

    return events
