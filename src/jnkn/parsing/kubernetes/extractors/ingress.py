from typing import Generator, Union

try:
    import yaml
except ImportError:
    yaml = None

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class IngressExtractor:
    """Extract Ingress definitions and link to Services."""

    name = "k8s_ingress"
    priority = 80

    def can_extract(self, ctx: ExtractionContext) -> bool:
        if yaml is None:
            return False
        return "Ingress" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        try:
            documents = yaml.safe_load_all(ctx.text)
        except yaml.YAMLError:
            return

        for doc in documents:
            if not doc or not isinstance(doc, dict):
                continue
            if doc.get("kind") != "Ingress":
                continue

            metadata = doc.get("metadata", {})
            spec = doc.get("spec", {})

            name = metadata.get("name", "")
            namespace = metadata.get("namespace", "default")

            ingress_id = f"k8s:{namespace}/ingress/{name}"

            yield Node(
                id=ingress_id,
                name=name,
                type=NodeType.INFRA_RESOURCE,
                path=str(ctx.file_path),
                metadata={
                    "k8s_kind": "Ingress",
                    "namespace": namespace,
                    "hosts": self._extract_hosts(spec),
                },
            )

            # Link file to ingress
            yield Edge(
                source_id=ctx.file_id,
                target_id=ingress_id,
                type=RelationshipType.CONTAINS,
            )

            # Extract backend services
            for rule in spec.get("rules", []):
                http = rule.get("http", {})
                for path in http.get("paths", []):
                    backend = path.get("backend", {})

                    # Handle both v1 (service.name) and v1beta1 (serviceName) formats
                    svc_name = None
                    if "service" in backend:
                        svc_name = backend["service"].get("name")
                    elif "serviceName" in backend:
                        svc_name = backend.get("serviceName")

                    if svc_name:
                        svc_id = f"k8s:{namespace}/service/{svc_name}"

                        yield Edge(
                            source_id=ingress_id,
                            target_id=svc_id,
                            type=RelationshipType.DEPENDS_ON,
                            metadata={
                                "path": path.get("path"),
                                "host": rule.get("host"),
                                "relation": "routes_to",
                            },
                        )

    def _extract_hosts(self, spec: dict) -> list:
        hosts = []
        for rule in spec.get("rules", []):
            if "host" in rule:
                hosts.append(rule["host"])
        return hosts
