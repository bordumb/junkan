"""
Kubernetes Manifest Parser.

This module provides a parser for Kubernetes YAML manifests. It handles the extraction
of workloads, environment variables, configuration maps, secrets, and their
interdependencies.

It supports both single-document and multi-document (--- separated) YAML files.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Union

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

    Attributes:
        name (str): The name of the environment variable.
        value (Optional[str]): Hardcoded string value, if present.
        config_map_name (Optional[str]): Name of the referenced ConfigMap.
        config_map_key (Optional[str]): Key within the ConfigMap.
        secret_name (Optional[str]): Name of the referenced Secret.
        secret_key (Optional[str]): Key within the Secret.
        field_ref (Optional[str]): Field reference (e.g. status.podIP).
    """
    name: str
    value: Optional[str] = None
    config_map_name: Optional[str] = None
    config_map_key: Optional[str] = None
    secret_name: Optional[str] = None
    secret_key: Optional[str] = None
    field_ref: Optional[str] = None

    @property
    def is_direct_value(self) -> bool:
        """bool: True if the variable uses a hardcoded value."""
        return self.value is not None

    @property
    def is_config_map_ref(self) -> bool:
        """bool: True if the variable references a ConfigMap."""
        return self.config_map_name is not None

    @property
    def is_secret_ref(self) -> bool:
        """bool: True if the variable references a Secret."""
        return self.secret_name is not None


class KubernetesParser(LanguageParser):
    """
    Parser for Kubernetes YAML files.

    This parser uses heuristics to distinguish Kubernetes manifests from other
    YAML files (like CI configs). It extracts detailed information about
    workloads (Deployments, StatefulSets, etc.) and their configuration dependencies.
    """

    WORKLOAD_KINDS = {
        "Deployment", "StatefulSet", "Job", "CronJob",
        "DaemonSet", "ReplicaSet", "Pod",
    }

    def __init__(self, context: Optional[ParserContext] = None):
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

    def can_parse(self, file_path: Path, content: Optional[bytes] = None) -> bool:
        """
        Heuristically check if a file is a Kubernetes manifest.

        Since `.yaml` is a generic extension, this method checks for:
        1. File path indicators (e.g. directories named 'k8s', 'charts').
        2. Filename patterns (e.g. 'deployment.yaml', 'service.yaml').
        3. File content markers (e.g. 'apiVersion:', 'kind:').

        Args:
            file_path (Path): Path to the file.
            content (Optional[bytes]): File content for deep inspection.

        Returns:
            bool: True if the file appears to be a Kubernetes manifest.
        """
        if file_path.suffix.lower() not in self.extensions:
            return False

        # 1. Directory heuristics
        k8s_indicators = {
            "kubernetes", "k8s", "manifests", "deploy",
            "deployments", "helm", "charts", "templates",
        }
        for part in file_path.parts:
            if part.lower() in k8s_indicators:
                return True

        # 2. Filename heuristics
        name = file_path.stem.lower()
        k8s_patterns = {
            "deployment", "service", "ingress", "configmap",
            "secret", "statefulset", "daemonset", "job",
            "cronjob", "namespace", "pod", "values",
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
        context: Optional[ParserContext] = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a Kubernetes YAML file and extract graph elements.

        Supports multi-document YAML files.

        Args:
            file_path (Path): Path to the file.
            content (bytes): File content.
            context (Optional[ParserContext]): Context override.

        Yields:
            Union[Node, Edge]: Nodes for resources (Deployments, ConfigMaps) and
            Edges for relationships (env var usage, mounting).
        """
        from ...core.types import ScanMetadata

        if not YAML_AVAILABLE:
            return

        # 1. Yield the file node itself
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

        # 2. Parse YAML content
        try:
            text = content.decode(self._context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception:
                return

        try:
            documents = list(yaml.safe_load_all(text))
        except yaml.YAMLError:
            return

        # 3. Process documents
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
        """Internal helper to process a single K8s resource dict."""
        kind = doc.get("kind", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")
        api_version = doc.get("apiVersion", "")

        if not kind or not name:
            return

        # Generate K8s node ID
        if namespace:
            k8s_id = f"k8s:{namespace}/{kind.lower()}/{name}"
        else:
            k8s_id = f"k8s:{kind.lower()}/{name}"

        # Determine node type based on kind
        node_type = NodeType.INFRA_RESOURCE
        if kind == "Secret":
            node_type = NodeType.SECRET
        elif kind == "ConfigMap":
            node_type = NodeType.CONFIG_KEY

        # Yield the resource node
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

        # Link file -> resource
        yield Edge(
            source_id=file_id,
            target_id=k8s_id,
            type=RelationshipType.PROVISIONS,
        )

        # Extract workload specifics (env vars, volumes)
        if kind in self.WORKLOAD_KINDS:
            pod_spec = self._get_pod_spec(doc)
            if pod_spec:
                containers = pod_spec.get("containers", [])
                for container in containers:
                    # 1. Env vars
                    env_list = container.get("env", [])
                    for env_var in self._extract_env_vars(env_list):
                        env_id = f"env:{env_var.name}"
                        
                        yield Node(
                            id=env_id,
                            name=env_var.name,
                            type=NodeType.ENV_VAR,
                            metadata={"k8s_resource": k8s_id},
                        )
                        yield Edge(
                            source_id=k8s_id,
                            target_id=env_id,
                            type=RelationshipType.PROVIDES,
                        )

                        # Link to referenced ConfigMaps/Secrets
                        if env_var.is_config_map_ref and env_var.config_map_name:
                            cm_id = f"k8s:{namespace}/configmap/{env_var.config_map_name}"
                            yield Edge(
                                source_id=env_id,
                                target_id=cm_id,
                                type=RelationshipType.READS
                            )
                        
                        if env_var.is_secret_ref and env_var.secret_name:
                            secret_id = f"k8s:{namespace}/secret/{env_var.secret_name}"
                            yield Edge(
                                source_id=env_id,
                                target_id=secret_id,
                                type=RelationshipType.READS
                            )

                    # 2. envFrom references
                    for env_from in container.get("envFrom", []):
                        if "configMapRef" in env_from:
                            cm_name = env_from["configMapRef"].get("name")
                            if cm_name:
                                cm_id = f"k8s:{namespace}/configmap/{cm_name}"
                                yield Edge(source_id=k8s_id, target_id=cm_id, type=RelationshipType.READS)
                        if "secretRef" in env_from:
                            secret_name = env_from["secretRef"].get("name")
                            if secret_name:
                                secret_id = f"k8s:{namespace}/secret/{secret_name}"
                                yield Edge(source_id=k8s_id, target_id=secret_id, type=RelationshipType.READS)

    def _get_pod_spec(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Extract PodSpec from various workload kinds."""
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
        """Convert raw env list to structured K8sEnvVar objects."""
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


def create_kubernetes_parser(context: Optional[ParserContext] = None) -> KubernetesParser:
    """Factory function for KubernetesParser."""
    return KubernetesParser(context)
