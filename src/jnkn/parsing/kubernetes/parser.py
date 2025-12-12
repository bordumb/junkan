"""
Kubernetes Manifest Parser.

This module provides a parser for Kubernetes YAML manifests. It handles the extraction
of workloads, environment variables, configuration maps, secrets, and their
interdependencies.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, List, Set, Union

try:
    import yaml

    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)

logger = logging.getLogger(__name__)


@dataclass
class K8sEnvVar:
    """
    Represents a detected environment variable in a Kubernetes container spec.
    """

    name: str
    value: str | None = None
    config_map_name: str | None = None
    config_map_key: str | None = None
    secret_name: str | None = None
    secret_key: str | None = None
    field_ref: str | None = None

    @property
    def is_direct_value(self) -> bool:
        return self.value is not None

    @property
    def is_config_map_ref(self) -> bool:
        return self.config_map_name is not None

    @property
    def is_secret_ref(self) -> bool:
        return self.secret_name is not None


class KubernetesParser(LanguageParser):
    """
    Parser for Kubernetes YAML files.
    """

    WORKLOAD_KINDS = {
        "Deployment",
        "StatefulSet",
        "Job",
        "CronJob",
        "DaemonSet",
        "ReplicaSet",
        "Pod",
    }

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        if not YAML_AVAILABLE:
            self._logger = logging.getLogger(__name__)
            self._logger.warning("PyYAML not available, K8s parsing will be limited")

    @property
    def name(self) -> str:
        return "kubernetes"

    @property
    def extensions(self) -> Set[str]:
        return {".yaml", ".yml"}

    @property
    def description(self) -> str:
        return "Kubernetes YAML manifest parser"

    def get_capabilities(self) -> Set[ParserCapability]:
        return {
            ParserCapability.ENV_VARS,
            ParserCapability.CONFIGS,
            ParserCapability.SECRETS,
            ParserCapability.DEPENDENCIES,
        }

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        if file_path.suffix.lower() not in self.extensions:
            return False

        # 1. Directory heuristics
        k8s_indicators = {
            "kubernetes",
            "k8s",
            "manifests",
            "deploy",
            "deployments",
            "helm",
            "charts",
            "templates",
        }
        for part in file_path.parts:
            if part.lower() in k8s_indicators:
                return True

        # 2. Filename heuristics
        name = file_path.stem.lower()
        k8s_patterns = {
            "deployment",
            "service",
            "ingress",
            "configmap",
            "secret",
            "statefulset",
            "daemonset",
            "job",
            "cronjob",
            "namespace",
            "pod",
            "values",
        }
        for pattern in k8s_patterns:
            if pattern in name:
                return True

        # 3. Content heuristics
        if content:
            try:
                start = content[:500].decode("utf-8", errors="ignore")
                if "apiVersion:" in start and "kind:" in start:
                    return True
            except Exception:
                pass

        return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
        context: ParserContext | None = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        from ...core.types import ScanMetadata

        if not YAML_AVAILABLE:
            return

        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception:
            file_hash = ""

        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="yaml",
            file_hash=file_hash,
        )

        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception:
                return

        try:
            documents = list(yaml.safe_load_all(text))
        except yaml.YAMLError:
            return

        for doc in documents:
            if not doc or not isinstance(doc, dict):
                continue
            if "apiVersion" not in doc or "kind" not in doc:
                continue

            yield from self._process_document(file_path, file_id, doc)

    def _process_document(
        self,
        file_path: Path,
        file_id: str,
        doc: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")
        api_version = doc.get("apiVersion", "")

        if not kind or not name:
            return

        if namespace:
            k8s_id = f"k8s:{namespace}/{kind.lower()}/{name}"
        else:
            k8s_id = f"k8s:{kind.lower()}/{name}"

        node_type = NodeType.INFRA_RESOURCE
        if kind == "Secret":
            node_type = NodeType.SECRET
        elif kind == "ConfigMap":
            node_type = NodeType.CONFIG_KEY

        yield Node(
            id=k8s_id,
            name=name,
            type=node_type,
            path=str(file_path),
            metadata={
                "k8s_kind": kind,
                "k8s_api_version": api_version,
                "namespace": namespace,
            },
        )

        yield Edge(
            source_id=file_id,
            target_id=k8s_id,
            type=RelationshipType.PROVISIONS,
        )

        # Handle Ingress
        if kind == "Ingress":
            yield from self._process_ingress(doc, k8s_id, namespace)

        # Handle Workloads
        if kind in self.WORKLOAD_KINDS:
            yield from self._process_workload(doc, k8s_id, namespace)

    def _process_ingress(self, doc: Dict[str, Any], ingress_id: str, namespace: str):
        """Extract backend services from Ingress."""
        spec = doc.get("spec", {})

        # Helper to yield edge
        def link_service(svc_name):
            if not svc_name:
                return
            svc_id = f"k8s:{namespace}/service/{svc_name}"
            # We don't yield the service node itself (it might be defined elsewhere)
            # but we create the edge. The graph builder handles missing nodes gracefully usually,
            # or we assume the service definition exists in the scan.
            yield Edge(
                source_id=ingress_id,
                target_id=svc_id,
                type=RelationshipType.ROUTES_TO,  # Custom type or mapped to DEPENDS_ON
                metadata={"type": "routes_to"},
            )

        # Default backend
        default_backend = spec.get("defaultBackend", {})
        if "service" in default_backend:
            link_service(default_backend["service"].get("name"))

        # Rules
        for rule in spec.get("rules", []):
            http = rule.get("http", {})
            for path in http.get("paths", []):
                backend = path.get("backend", {})

                # Networking V1
                if "service" in backend:
                    yield from link_service(backend["service"].get("name"))
                # Legacy / other versions might use serviceName directly
                elif "serviceName" in backend:
                    yield from link_service(backend.get("serviceName"))

    def _process_workload(self, doc: Dict[str, Any], workload_id: str, namespace: str):
        """Extract env vars and volumes from workloads."""
        pod_spec = self._get_pod_spec(doc)
        if not pod_spec:
            return

        containers = pod_spec.get("containers", [])
        for container in containers:
            # Env vars
            env_list = container.get("env", [])
            for env_var in self._extract_env_vars(env_list):
                env_id = f"env:{env_var.name}"

                yield Node(
                    id=env_id,
                    name=env_var.name,
                    type=NodeType.ENV_VAR,
                    metadata={"k8s_resource": workload_id},
                )
                yield Edge(
                    source_id=workload_id,
                    target_id=env_id,
                    type=RelationshipType.PROVIDES,
                )

                if env_var.is_config_map_ref and env_var.config_map_name:
                    cm_id = f"k8s:{namespace}/configmap/{env_var.config_map_name}"
                    yield Node(
                        id=cm_id,
                        name=env_var.config_map_name,
                        type=NodeType.CONFIG_KEY,
                        metadata={"virtual": True},
                    )
                    yield Edge(source_id=env_id, target_id=cm_id, type=RelationshipType.READS)

                if env_var.is_secret_ref and env_var.secret_name:
                    secret_id = f"k8s:{namespace}/secret/{env_var.secret_name}"
                    yield Node(
                        id=secret_id,
                        name=env_var.secret_name,
                        type=NodeType.SECRET,
                        metadata={"virtual": True},
                    )
                    yield Edge(source_id=env_id, target_id=secret_id, type=RelationshipType.READS)

            # envFrom
            for env_from in container.get("envFrom", []):
                if "configMapRef" in env_from:
                    cm_name = env_from["configMapRef"].get("name")
                    if cm_name:
                        cm_id = f"k8s:{namespace}/configmap/{cm_name}"
                        yield Node(
                            id=cm_id,
                            name=cm_name,
                            type=NodeType.CONFIG_KEY,
                            metadata={"virtual": True},
                        )
                        yield Edge(
                            source_id=workload_id, target_id=cm_id, type=RelationshipType.READS
                        )
                if "secretRef" in env_from:
                    secret_name = env_from["secretRef"].get("name")
                    if secret_name:
                        secret_id = f"k8s:{namespace}/secret/{secret_name}"
                        yield Node(
                            id=secret_id,
                            name=secret_name,
                            type=NodeType.SECRET,
                            metadata={"virtual": True},
                        )
                        yield Edge(
                            source_id=workload_id, target_id=secret_id, type=RelationshipType.READS
                        )

    def _get_pod_spec(self, doc: Dict[str, Any]) -> Dict[str, Any] | None:
        kind = doc.get("kind", "")
        spec = doc.get("spec", {})

        if kind == "Pod":
            return spec
        elif kind in ("Deployment", "ReplicaSet", "DaemonSet", "StatefulSet", "Job"):
            return spec.get("template", {}).get("spec", {})
        elif kind == "CronJob":
            return spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {})
        return None

    def _extract_env_vars(self, env_list: List[Dict[str, Any]]) -> List[K8sEnvVar]:
        result: List[K8sEnvVar] = []
        for env in env_list:
            name = env.get("name")
            if not name:
                continue

            var = K8sEnvVar(name=name)
            if "value" in env:
                var.value = str(env["value"])
            elif "valueFrom" in env:
                vf = env["valueFrom"]
                if "configMapKeyRef" in vf:
                    var.config_map_name = vf["configMapKeyRef"].get("name")
                    var.config_map_key = vf["configMapKeyRef"].get("key")
                elif "secretKeyRef" in vf:
                    var.secret_name = vf["secretKeyRef"].get("name")
                    var.secret_key = vf["secretKeyRef"].get("key")

            result.append(var)
        return result


def create_kubernetes_parser(context: ParserContext | None = None) -> KubernetesParser:
    return KubernetesParser(context)
