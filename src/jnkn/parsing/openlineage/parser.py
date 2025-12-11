"""
OpenLineage Parser for jnkn.

This parser imports runtime lineage data from OpenLineage/Marquez,
enriching jnkn's static analysis with observed production dependencies.

OpenLineage Event Format:
    {
        "eventType": "COMPLETE",
        "eventTime": "2024-12-09T10:00:00Z",
        "job": {"namespace": "spark", "name": "daily_etl"},
        "inputs": [{"namespace": "postgres", "name": "public.users"}],
        "outputs": [{"namespace": "s3", "name": "warehouse/dim_users"}],
        "run": {"runId": "abc-123"}
    }

Usage:
    # From exported JSON file
    parser = OpenLineageParser()
    for item in parser.parse(Path("lineage_events.json"), content):
        if isinstance(item, Node):
            graph.add_node(item)
        elif isinstance(item, Edge):
            graph.add_edge(item)
    
    # From Marquez API
    parser = OpenLineageParser()
    events = parser.fetch_from_marquez("http://marquez:5000", namespace="spark")
    for item in parser.parse_events(events):
        ...
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Set, Tuple, Union

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


# =============================================================================
# Data Models
# =============================================================================

class NodeType(Enum):
    """Types of nodes in the dependency graph."""
    CODE_FILE = "code_file"
    CODE_ENTITY = "code_entity"
    ENV_VAR = "env_var"
    INFRA_RESOURCE = "infra_resource"
    DATA_ASSET = "data_asset"
    CONFIG_KEY = "config_key"
    JOB = "job"  # OpenLineage-specific


class RelationshipType(Enum):
    """Types of relationships between nodes."""
    IMPORTS = "imports"
    READS = "reads"
    WRITES = "writes"
    PROVIDES = "provides"
    CONFIGURES = "configures"
    TRANSFORMS = "transforms"
    DEPENDS_ON = "depends_on"


@dataclass
class Node:
    """A node in the dependency graph."""
    id: str
    name: str
    type: NodeType
    path: str | None = None
    language: str | None = None
    file_hash: str | None = None
    tokens: Tuple[str, ...] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "path": self.path,
            "tokens": list(self.tokens),
            "metadata": self.metadata,
        }


@dataclass
class Edge:
    """An edge (relationship) in the dependency graph."""
    source_id: str
    target_id: str
    type: RelationshipType
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.type.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


# =============================================================================
# OpenLineage Parser
# =============================================================================

class OpenLineageParser:
    """
    Parser for OpenLineage events.
    
    Converts runtime lineage events into jnkn's Node/Edge format,
    enabling correlation between static code analysis and observed
    production data flows.
    
    Confidence Levels:
        - Runtime lineage has confidence=1.0 (observed, not inferred)
        - This is higher than static analysis which may miss dynamic patterns
    
    Example:
        parser = OpenLineageParser()
        
        # From file
        for item in parser.parse(Path("events.json"), content):
            graph.add(item)
        
        # From Marquez API
        events = parser.fetch_from_marquez("http://marquez:5000")
        for item in parser.parse_events(events):
            graph.add(item)
    """

    def __init__(self, namespace_filter: str | None = None):
        """
        Initialize the parser.
        
        Args:
            namespace_filter: Optional regex to filter namespaces
        """
        self._namespace_filter = namespace_filter
        self._seen_nodes: Set[str] = set()
        self._seen_edges: Set[Tuple[str, str, str]] = set()

    @property
    def name(self) -> str:
        return "openlineage"

    @property
    def extensions(self) -> Set[str]:
        return {".json"}

    # =========================================================================
    # Main Parse Methods
    # =========================================================================

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Iterator[Union[Node, Edge]]:
        """
        Parse OpenLineage events from a JSON file.
        
        Supports both single events and arrays of events.
        
        Args:
            file_path: Path to JSON file
            content: File content as bytes
            
        Yields:
            Node and Edge objects
        """
        try:
            text = content.decode("utf-8")
            data = json.loads(text)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise ValueError(f"Invalid JSON in {file_path}: {e}")

        # Handle single event or array
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            # Could be a single event or a wrapper with "events" key
            if "events" in data:
                events = data["events"]
            else:
                events = [data]
        else:
            raise ValueError(f"Unexpected data format in {file_path}")

        yield from self.parse_events(events)

    def parse_events(
        self,
        events: List[Dict[str, Any]],
    ) -> Iterator[Union[Node, Edge]]:
        """
        Parse a list of OpenLineage events.
        
        Args:
            events: List of OpenLineage event dictionaries
            
        Yields:
            Node and Edge objects (deduplicated)
        """
        self._seen_nodes.clear()
        self._seen_edges.clear()

        for event in events:
            yield from self._parse_event(event)

    def _parse_event(
        self,
        event: Dict[str, Any],
    ) -> Iterator[Union[Node, Edge]]:
        """Parse a single OpenLineage event."""

        # Skip non-COMPLETE events (we want final state)
        event_type = event.get("eventType", "")
        if event_type not in ("COMPLETE", "RUNNING"):
            return

        # Extract job info
        job = event.get("job", {})
        job_namespace = job.get("namespace", "default")
        job_name = job.get("name", "unknown")

        # Apply namespace filter
        if self._namespace_filter:
            if not re.match(self._namespace_filter, job_namespace):
                return

        # Create job node
        job_id = f"job:{job_namespace}/{job_name}"
        if job_id not in self._seen_nodes:
            self._seen_nodes.add(job_id)
            yield self._create_job_node(job_namespace, job_name, job)

        # Process inputs (datasets the job reads)
        for input_dataset in event.get("inputs", []):
            yield from self._process_dataset(
                dataset=input_dataset,
                job_id=job_id,
                direction="input",
                event=event,
            )

        # Process outputs (datasets the job writes)
        for output_dataset in event.get("outputs", []):
            yield from self._process_dataset(
                dataset=output_dataset,
                job_id=job_id,
                direction="output",
                event=event,
            )

    def _process_dataset(
        self,
        dataset: Dict[str, Any],
        job_id: str,
        direction: str,
        event: Dict[str, Any],
    ) -> Iterator[Union[Node, Edge]]:
        """Process an input or output dataset."""

        namespace = dataset.get("namespace", "default")
        name = dataset.get("name", "unknown")

        # Create dataset node
        dataset_id = f"data:{namespace}/{name}"

        if dataset_id not in self._seen_nodes:
            self._seen_nodes.add(dataset_id)
            yield self._create_dataset_node(namespace, name, dataset)

        # Create edge (job -> dataset for writes, dataset -> job for reads)
        if direction == "input":
            # Job READS from dataset
            edge_key = (job_id, dataset_id, "reads")
            if edge_key not in self._seen_edges:
                self._seen_edges.add(edge_key)
                yield Edge(
                    source_id=job_id,
                    target_id=dataset_id,
                    type=RelationshipType.READS,
                    confidence=1.0,  # Observed in production
                    metadata={
                        "source": "openlineage",
                        "event_time": event.get("eventTime"),
                    },
                )
        else:
            # Job WRITES to dataset
            edge_key = (job_id, dataset_id, "writes")
            if edge_key not in self._seen_edges:
                self._seen_edges.add(edge_key)
                yield Edge(
                    source_id=job_id,
                    target_id=dataset_id,
                    type=RelationshipType.WRITES,
                    confidence=1.0,  # Observed in production
                    metadata={
                        "source": "openlineage",
                        "event_time": event.get("eventTime"),
                    },
                )

        # Extract column lineage if present (InputDatasetFacet)
        facets = dataset.get("facets", {})

        # Schema facet - extract columns
        schema_facet = facets.get("schema", {})
        if schema_facet and "fields" in schema_facet:
            for field_info in schema_facet["fields"]:
                col_name = field_info.get("name")
                if col_name:
                    col_id = f"column:{namespace}/{name}/{col_name}"
                    if col_id not in self._seen_nodes:
                        self._seen_nodes.add(col_id)
                        yield self._create_column_node(
                            namespace, name, col_name, field_info
                        )

        # Column lineage facet
        col_lineage = facets.get("columnLineage", {})
        if col_lineage and "fields" in col_lineage:
            for col_name, lineage_info in col_lineage["fields"].items():
                for input_field in lineage_info.get("inputFields", []):
                    src_namespace = input_field.get("namespace", namespace)
                    src_name = input_field.get("name", name)
                    src_field = input_field.get("field", "")

                    if src_field:
                        src_col_id = f"column:{src_namespace}/{src_name}/{src_field}"
                        tgt_col_id = f"column:{namespace}/{name}/{col_name}"

                        edge_key = (src_col_id, tgt_col_id, "transforms")
                        if edge_key not in self._seen_edges:
                            self._seen_edges.add(edge_key)
                            yield Edge(
                                source_id=src_col_id,
                                target_id=tgt_col_id,
                                type=RelationshipType.TRANSFORMS,
                                confidence=1.0,
                                metadata={
                                    "source": "openlineage",
                                    "transformation": input_field.get("transformations", []),
                                },
                            )

    # =========================================================================
    # Node Creation Helpers
    # =========================================================================

    def _create_job_node(
        self,
        namespace: str,
        name: str,
        job: Dict[str, Any],
    ) -> Node:
        """Create a Node for a job."""

        # Tokenize for stitching with code files
        tokens = self._tokenize(name)

        return Node(
            id=f"job:{namespace}/{name}",
            name=name,
            type=NodeType.JOB,
            tokens=tokens,
            metadata={
                "namespace": namespace,
                "source": "openlineage",
                "facets": job.get("facets", {}),
            },
        )

    def _create_dataset_node(
        self,
        namespace: str,
        name: str,
        dataset: Dict[str, Any],
    ) -> Node:
        """Create a Node for a dataset (table, file, etc.)."""

        # Tokenize for stitching
        tokens = self._tokenize(name)

        # Extract additional info from facets
        facets = dataset.get("facets", {})
        schema_fields = []

        if "schema" in facets:
            schema_fields = [
                f.get("name") for f in facets["schema"].get("fields", [])
            ]

        return Node(
            id=f"data:{namespace}/{name}",
            name=name,
            type=NodeType.DATA_ASSET,
            tokens=tokens,
            metadata={
                "namespace": namespace,
                "source": "openlineage",
                "schema_fields": schema_fields,
                "facets": facets,
            },
        )

    def _create_column_node(
        self,
        namespace: str,
        table_name: str,
        column_name: str,
        field_info: Dict[str, Any],
    ) -> Node:
        """Create a Node for a column."""

        return Node(
            id=f"column:{namespace}/{table_name}/{column_name}",
            name=column_name,
            type=NodeType.DATA_ASSET,
            tokens=self._tokenize(column_name),
            metadata={
                "namespace": namespace,
                "table": table_name,
                "data_type": field_info.get("type"),
                "source": "openlineage",
            },
        )

    def _tokenize(self, name: str) -> Tuple[str, ...]:
        """Tokenize a name for cross-domain stitching."""
        # Split on common separators
        parts = re.split(r'[_\-./]', name.lower())
        # Filter out empty and very short tokens
        return tuple(p for p in parts if len(p) >= 2)

    # =========================================================================
    # Marquez API Integration
    # =========================================================================

    def fetch_from_marquez(
        self,
        base_url: str,
        namespace: str | None = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Fetch lineage events from Marquez API.
        
        Args:
            base_url: Marquez API base URL (e.g., "http://marquez:5000")
            namespace: Optional namespace to filter by
            limit: Maximum number of events to fetch
            
        Returns:
            List of OpenLineage events
        """
        if not HAS_REQUESTS:
            raise ImportError("requests library required for Marquez API. pip install requests")

        events = []

        # Fetch jobs
        jobs_url = f"{base_url}/api/v1/namespaces"
        if namespace:
            jobs_url = f"{base_url}/api/v1/namespaces/{namespace}/jobs"

        try:
            resp = requests.get(jobs_url, timeout=30)
            resp.raise_for_status()
            jobs_data = resp.json()

            # Fetch runs for each job to get lineage events
            for job in jobs_data.get("jobs", [])[:limit]:
                job_namespace = job.get("namespace", namespace or "default")
                job_name = job.get("name")

                runs_url = f"{base_url}/api/v1/namespaces/{job_namespace}/jobs/{job_name}/runs"
                runs_resp = requests.get(runs_url, timeout=30)

                if runs_resp.ok:
                    runs_data = runs_resp.json()
                    for run in runs_data.get("runs", [])[:10]:  # Latest 10 runs
                        # Convert Marquez run to OpenLineage event format
                        event = self._marquez_run_to_event(job, run)
                        if event:
                            events.append(event)

        except requests.RequestException as e:
            raise ConnectionError(f"Failed to fetch from Marquez: {e}")

        return events

    def _marquez_run_to_event(
        self,
        job: Dict[str, Any],
        run: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        """Convert a Marquez run to OpenLineage event format."""

        if run.get("state") != "COMPLETED":
            return None

        return {
            "eventType": "COMPLETE",
            "eventTime": run.get("endedAt"),
            "job": {
                "namespace": job.get("namespace"),
                "name": job.get("name"),
            },
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


# =============================================================================
# Convenience Functions
# =============================================================================

def parse_openlineage_file(file_path: str) -> Tuple[List[Node], List[Edge]]:
    """
    Parse an OpenLineage JSON file and return nodes and edges.
    
    Args:
        file_path: Path to JSON file with OpenLineage events
        
    Returns:
        Tuple of (nodes, edges)
    """
    path = Path(file_path)
    content = path.read_bytes()

    parser = OpenLineageParser()

    nodes = []
    edges = []

    for item in parser.parse(path, content):
        if isinstance(item, Node):
            nodes.append(item)
        elif isinstance(item, Edge):
            edges.append(item)

    return nodes, edges


def fetch_and_parse_marquez(
    base_url: str,
    namespace: str | None = None,
) -> Tuple[List[Node], List[Edge]]:
    """
    Fetch from Marquez API and parse into nodes and edges.
    
    Args:
        base_url: Marquez API URL
        namespace: Optional namespace filter
        
    Returns:
        Tuple of (nodes, edges)
    """
    parser = OpenLineageParser()
    events = parser.fetch_from_marquez(base_url, namespace)

    nodes = []
    edges = []

    for item in parser.parse_events(events):
        if isinstance(item, Node):
            nodes.append(item)
        elif isinstance(item, Edge):
            edges.append(item)

    return nodes, edges


# =============================================================================
# Main (Demo)
# =============================================================================

if __name__ == "__main__":
    # Example OpenLineage events (as would be exported from Marquez or Spark)
    sample_events = [
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T10:00:00Z",
            "job": {
                "namespace": "spark",
                "name": "daily_user_etl"
            },
            "inputs": [
                {
                    "namespace": "postgres",
                    "name": "public.raw_users",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "user_id", "type": "INTEGER"},
                                {"name": "email", "type": "VARCHAR"},
                                {"name": "created_at", "type": "TIMESTAMP"}
                            ]
                        }
                    }
                },
                {
                    "namespace": "postgres",
                    "name": "public.user_events"
                }
            ],
            "outputs": [
                {
                    "namespace": "s3",
                    "name": "warehouse/dim_users",
                    "facets": {
                        "schema": {
                            "fields": [
                                {"name": "user_id", "type": "INTEGER"},
                                {"name": "email", "type": "VARCHAR"},
                                {"name": "event_count", "type": "INTEGER"},
                                {"name": "last_event_at", "type": "TIMESTAMP"}
                            ]
                        },
                        "columnLineage": {
                            "fields": {
                                "user_id": {
                                    "inputFields": [
                                        {"namespace": "postgres", "name": "public.raw_users", "field": "user_id"}
                                    ]
                                },
                                "event_count": {
                                    "inputFields": [
                                        {"namespace": "postgres", "name": "public.user_events", "field": "event_id", "transformations": ["count"]}
                                    ]
                                }
                            }
                        }
                    }
                }
            ],
            "run": {"runId": "run-001"}
        },
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T11:00:00Z",
            "job": {
                "namespace": "spark",
                "name": "user_metrics_aggregator"
            },
            "inputs": [
                {
                    "namespace": "s3",
                    "name": "warehouse/dim_users"
                }
            ],
            "outputs": [
                {
                    "namespace": "s3",
                    "name": "warehouse/agg_user_metrics"
                }
            ],
            "run": {"runId": "run-002"}
        },
        {
            "eventType": "COMPLETE",
            "eventTime": "2024-12-09T12:00:00Z",
            "job": {
                "namespace": "spark",
                "name": "executive_dashboard_loader"
            },
            "inputs": [
                {
                    "namespace": "s3",
                    "name": "warehouse/agg_user_metrics"
                }
            ],
            "outputs": [
                {
                    "namespace": "redshift",
                    "name": "analytics.exec_dashboard"
                }
            ],
            "run": {"runId": "run-003"}
        }
    ]

    print("=" * 70)
    print("OPENLINEAGE PARSER DEMO")
    print("=" * 70)

    parser = OpenLineageParser()

    nodes = []
    edges = []

    for item in parser.parse_events(sample_events):
        if isinstance(item, Node):
            nodes.append(item)
        elif isinstance(item, Edge):
            edges.append(item)

    print(f"\n📊 Parsed {len(sample_events)} events")
    print(f"   Nodes: {len(nodes)}")
    print(f"   Edges: {len(edges)}")

    print("\n🔷 NODES:")
    for node in nodes:
        print(f"   [{node.type.value:12}] {node.id}")

    print("\n🔗 EDGES:")
    for edge in edges:
        print(f"   {edge.source_id}")
        print(f"     --[{edge.type.value}]--> {edge.target_id}")
        print()

    # Show the lineage chain
    print("=" * 70)
    print("LINEAGE CHAIN (from runtime data)")
    print("=" * 70)
    print("""
    postgres/public.raw_users ─────┐
                                   ├──▶ spark/daily_user_etl ──▶ s3/warehouse/dim_users
    postgres/public.user_events ───┘                                      │
                                                                          ▼
                                              spark/user_metrics_aggregator
                                                                          │
                                                                          ▼
                                                     s3/warehouse/agg_user_metrics
                                                                          │
                                                                          ▼
                                              spark/executive_dashboard_loader
                                                                          │
                                                                          ▼
                                                  redshift/analytics.exec_dashboard
    """)

    print("\n💡 This runtime lineage can be MERGED with jnkn's static analysis")
    print("   to create a complete pre-merge impact analysis system.")
