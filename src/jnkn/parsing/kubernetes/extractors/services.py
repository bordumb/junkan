import hashlib
import json
from typing import Generator, Union

try:
    import yaml
except ImportError:
    yaml = None

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


def _selector_hash(selector: dict) -> str:
    """Generate a deterministic hash for a label selector."""
    s = json.dumps(selector, sort_keys=True)
    return hashlib.md5(s.encode()).hexdigest()[:8]


class ServiceExtractor:
    """Extract Service definitions and link to workloads via selectors."""

    name = "k8s_services"
    priority = 90

    def can_extract(self, ctx: ExtractionContext) -> bool:
        if yaml is None:
            return False
        return '"kind": "Service"' in ctx.text or "kind: Service" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        try:
            documents = yaml.safe_load_all(ctx.text)
        except yaml.YAMLError:
            return

        for doc in documents:
            if not doc or not isinstance(doc, dict):
                continue
            if doc.get("kind") != "Service":
                continue

            metadata = doc.get("metadata", {})
            spec = doc.get("spec", {})

            name = metadata.get("name", "")
            namespace = metadata.get("namespace", "default")
            selector = spec.get("selector", {})

            svc_id = f"k8s:{namespace}/service/{name}"

            yield Node(
                id=svc_id,
                name=name,
                type=NodeType.INFRA_RESOURCE,
                path=str(ctx.file_path),
                metadata={
                    "k8s_kind": "Service",
                    "namespace": namespace,
                    "selector": selector,
                    "type": spec.get("type", "ClusterIP"),
                    "ports": spec.get("ports", []),
                },
            )

            # Link to file
            yield Edge(
                source_id=ctx.file_id,
                target_id=svc_id,
                type=RelationshipType.CONTAINS,
            )

            # Create selector-based relationship (resolved later by stitcher)
            if selector:
                selector_node_id = f"k8s:selector:{namespace}/{_selector_hash(selector)}"

                # Store selector for later matching
                yield Node(
                    id=selector_node_id,
                    name=f"selector:{name}",
                    type=NodeType.CONFIG_KEY,
                    metadata={
                        "selector": selector,
                        "namespace": namespace,
                        "virtual": True,
                    },
                )

                yield Edge(
                    source_id=svc_id,
                    target_id=selector_node_id,
                    type=RelationshipType.CONFIGURES,
                )
