"""
Kubernetes Manifest Parser for jnkn.

This parser provides comprehensive extraction from Kubernetes YAML manifests:
- Deployments, StatefulSets, Jobs, CronJobs
- Environment variables from container specs
- ConfigMap and Secret references
- Service dependencies
- Resource requests and limits

Supports both single-document and multi-document YAML files.

Features:
- Environment variable extraction (direct, configMapKeyRef, secretKeyRef)
- ConfigMap and Secret reference tracking
- Volume mount analysis
- Service account references
- Image extraction
"""

from pathlib import Path
from typing import Generator, List, Optional, Dict, Any, Set, Union
from dataclasses import dataclass, field
import logging

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
    ParseError,
)
from ...core.types import Node, Edge, NodeType, RelationshipType

logger = logging.getLogger(__name__)


@dataclass
class K8sEnvVar:
    """
    Represents a Kubernetes environment variable.
    
    Can be a direct value, or a reference to ConfigMap or Secret.
    """
    name: str
    value: Optional[str] = None
    config_map_name: Optional[str] = None
    config_map_key: Optional[str] = None
    secret_name: Optional[str] = None
    secret_key: Optional[str] = None
    field_ref: Optional[str] = None  # For fieldRef (e.g., metadata.name)
    
    @property
    def is_direct_value(self) -> bool:
        """Check if this is a direct value (not a reference)."""
        return self.value is not None
    
    @property
    def is_config_map_ref(self) -> bool:
        """Check if this references a ConfigMap."""
        return self.config_map_name is not None
    
    @property
    def is_secret_ref(self) -> bool:
        """Check if this references a Secret."""
        return self.secret_name is not None


@dataclass
class K8sResource:
    """
    Represents a Kubernetes resource (Deployment, StatefulSet, etc.)
    """
    kind: str
    name: str
    namespace: str
    api_version: str
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    env_vars: List[K8sEnvVar] = field(default_factory=list)
    config_maps: List[str] = field(default_factory=list)
    secrets: List[str] = field(default_factory=list)
    images: List[str] = field(default_factory=list)
    service_account: Optional[str] = None
    volumes: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def node_id(self) -> str:
        """Generate the jnkn node ID."""
        if self.namespace:
            return f"k8s:{self.namespace}/{self.kind.lower()}/{self.name}"
        return f"k8s:{self.kind.lower()}/{self.name}"


@dataclass
class K8sConfigMap:
    """Represents a Kubernetes ConfigMap."""
    name: str
    namespace: str
    data_keys: List[str] = field(default_factory=list)
    
    @property
    def node_id(self) -> str:
        if self.namespace:
            return f"k8s:{self.namespace}/configmap/{self.name}"
        return f"k8s:configmap/{self.name}"


@dataclass
class K8sSecret:
    """Represents a Kubernetes Secret."""
    name: str
    namespace: str
    type: str = "Opaque"
    data_keys: List[str] = field(default_factory=list)
    
    @property
    def node_id(self) -> str:
        if self.namespace:
            return f"k8s:{self.namespace}/secret/{self.name}"
        return f"k8s:secret/{self.name}"


class KubernetesParser(LanguageParser):
    """
    Parser for Kubernetes YAML manifests.
    
    Extracts:
    - Workloads (Deployments, StatefulSets, Jobs, CronJobs, DaemonSets)
    - Environment variables and their sources
    - ConfigMap and Secret references
    - Service dependencies
    - Volume mounts
    - Container images
    """
    
    # Workload kinds we specifically handle for env var extraction
    WORKLOAD_KINDS = {
        "Deployment", "StatefulSet", "Job", "CronJob",
        "DaemonSet", "ReplicaSet", "Pod",
    }
    
    # All kinds we track as nodes
    TRACKED_KINDS = WORKLOAD_KINDS | {
        "Service", "Ingress", "ConfigMap", "Secret",
        "ServiceAccount", "PersistentVolumeClaim",
        "HorizontalPodAutoscaler", "NetworkPolicy",
    }
    
    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        
        if not YAML_AVAILABLE:
            self._logger.warning("PyYAML not available, K8s parsing will be limited")
    
    @property
    def name(self) -> str:
        return "kubernetes"
    
    @property
    def extensions(self) -> List[str]:
        return [".yaml", ".yml"]
    
    @property
    def description(self) -> str:
        return "Kubernetes YAML manifest parser"
    
    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.ENV_VARS,
            ParserCapability.CONFIGS,
            ParserCapability.SECRETS,
            ParserCapability.DEPENDENCIES,
        ]
    
    def supports_file(self, file_path: Path) -> bool:
        """
        Check if this is likely a Kubernetes manifest.
        
        We do some heuristic checking since .yaml is very generic.
        """
        if file_path.suffix.lower() not in [".yaml", ".yml"]:
            return False
        
        # Check for k8s-related directory names
        k8s_indicators = {
            "kubernetes", "k8s", "manifests", "deploy",
            "deployments", "helm", "charts", "templates",
        }
        
        for part in file_path.parts:
            if part.lower() in k8s_indicators:
                return True
        
        # Check filename patterns
        name = file_path.stem.lower()
        k8s_patterns = {
            "deployment", "service", "ingress", "configmap",
            "secret", "statefulset", "daemonset", "job",
            "cronjob", "namespace", "pod", "values",
        }
        
        for pattern in k8s_patterns:
            if pattern in name:
                return True
        
        return False
    
    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a Kubernetes YAML manifest.
        
        Handles multi-document YAML files (separated by ---).
        """
        from ...core.types import ScanMetadata
        
        if not YAML_AVAILABLE:
            self._logger.error("PyYAML required for Kubernetes parsing")
            return
        
        # Create file node
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
        
        # Decode content
        try:
            text = content.decode(self._context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                self._logger.error(f"Failed to decode {file_path}: {e}")
                return
        
        # Parse YAML (handles multi-document)
        try:
            documents = list(yaml.safe_load_all(text))
        except yaml.YAMLError as e:
            self._logger.error(f"Failed to parse YAML {file_path}: {e}")
            return
        
        # Process each document
        for doc in documents:
            if not doc or not isinstance(doc, dict):
                continue
            
            # Check if this looks like a K8s resource
            if "apiVersion" not in doc or "kind" not in doc:
                continue
            
            yield from self._process_document(file_path, file_id, doc)
    
    def _process_document(
        self,
        file_path: Path,
        file_id: str,
        doc: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Process a single Kubernetes resource document."""
        kind = doc.get("kind", "")
        api_version = doc.get("apiVersion", "")
        metadata = doc.get("metadata", {})
        name = metadata.get("name", "")
        namespace = metadata.get("namespace", "default")
        labels = metadata.get("labels", {})
        annotations = metadata.get("annotations", {})
        
        if not kind or not name:
            return
        
        # Create node ID
        if namespace:
            k8s_id = f"k8s:{namespace}/{kind.lower()}/{name}"
        else:
            k8s_id = f"k8s:{kind.lower()}/{name}"
        
        # Extract resource-specific information
        env_vars: List[K8sEnvVar] = []
        config_maps: Set[str] = set()
        secrets: Set[str] = set()
        images: List[str] = []
        service_account: Optional[str] = None
        
        # Process workloads
        if kind in self.WORKLOAD_KINDS:
            # Get the pod spec
            pod_spec = self._get_pod_spec(doc)
            
            if pod_spec:
                # Extract service account
                service_account = pod_spec.get("serviceAccountName")
                
                # Process containers
                containers = pod_spec.get("containers", [])
                init_containers = pod_spec.get("initContainers", [])
                
                for container in containers + init_containers:
                    # Extract image
                    image = container.get("image")
                    if image:
                        images.append(image)
                    
                    # Extract environment variables
                    env_vars.extend(
                        self._extract_env_vars(container.get("env", []))
                    )
                    
                    # Extract envFrom references
                    for env_from in container.get("envFrom", []):
                        if "configMapRef" in env_from:
                            config_maps.add(env_from["configMapRef"].get("name", ""))
                        if "secretRef" in env_from:
                            secrets.add(env_from["secretRef"].get("name", ""))
                
                # Extract from volumes
                for volume in pod_spec.get("volumes", []):
                    if "configMap" in volume:
                        config_maps.add(volume["configMap"].get("name", ""))
                    if "secret" in volume:
                        secrets.add(volume["secret"].get("secretName", ""))
        
        # Handle ConfigMaps
        elif kind == "ConfigMap":
            data_keys = list((doc.get("data", {}) or {}).keys())
            binary_keys = list((doc.get("binaryData", {}) or {}).keys())
            all_keys = data_keys + binary_keys
            
            yield Node(
                id=k8s_id,
                name=name,
                type=NodeType.CONFIG_KEY,
                path=str(file_path),
                metadata={
                    "k8s_kind": kind,
                    "k8s_api_version": api_version,
                    "namespace": namespace,
                    "labels": labels,
                    "data_keys": all_keys,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=k8s_id,
                type=RelationshipType.PROVISIONS,
            )
            return
        
        # Handle Secrets
        elif kind == "Secret":
            data_keys = list((doc.get("data", {}) or {}).keys())
            string_keys = list((doc.get("stringData", {}) or {}).keys())
            all_keys = data_keys + string_keys
            secret_type = doc.get("type", "Opaque")
            
            yield Node(
                id=k8s_id,
                name=name,
                type=NodeType.SECRET,
                path=str(file_path),
                metadata={
                    "k8s_kind": kind,
                    "k8s_api_version": api_version,
                    "namespace": namespace,
                    "labels": labels,
                    "secret_type": secret_type,
                    "data_keys": all_keys,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=k8s_id,
                type=RelationshipType.PROVISIONS,
            )
            return
        
        # Handle Services
        elif kind == "Service":
            spec = doc.get("spec", {})
            selector = spec.get("selector", {})
            ports = spec.get("ports", [])
            service_type = spec.get("type", "ClusterIP")
            
            yield Node(
                id=k8s_id,
                name=name,
                type=NodeType.INFRA_RESOURCE,
                path=str(file_path),
                metadata={
                    "k8s_kind": kind,
                    "k8s_api_version": api_version,
                    "namespace": namespace,
                    "labels": labels,
                    "selector": selector,
                    "ports": [p.get("port") for p in ports],
                    "service_type": service_type,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=k8s_id,
                type=RelationshipType.PROVISIONS,
            )
            return
        
        # Create the main resource node
        yield Node(
            id=k8s_id,
            name=name,
            type=NodeType.INFRA_RESOURCE,
            path=str(file_path),
            metadata={
                "k8s_kind": kind,
                "k8s_api_version": api_version,
                "namespace": namespace,
                "labels": labels,
                "annotations": annotations,
                "images": images,
                "service_account": service_account,
                "env_var_count": len(env_vars),
                "config_maps": list(config_maps),
                "secrets": list(secrets),
            },
        )
        
        yield Edge(
            source_id=file_id,
            target_id=k8s_id,
            type=RelationshipType.PROVISIONS,
        )
        
        # Create env var nodes and edges
        for env_var in env_vars:
            env_id = f"env:{env_var.name}"
            
            # Determine the source of the env var
            source_info = {}
            if env_var.is_config_map_ref:
                source_info = {
                    "source_type": "configMapKeyRef",
                    "config_map": env_var.config_map_name,
                    "key": env_var.config_map_key,
                }
            elif env_var.is_secret_ref:
                source_info = {
                    "source_type": "secretKeyRef",
                    "secret": env_var.secret_name,
                    "key": env_var.secret_key,
                }
            elif env_var.field_ref:
                source_info = {
                    "source_type": "fieldRef",
                    "field_path": env_var.field_ref,
                }
            elif env_var.is_direct_value:
                source_info = {
                    "source_type": "direct",
                    "value": env_var.value[:50] if env_var.value else None,
                }
            
            yield Node(
                id=env_id,
                name=env_var.name,
                type=NodeType.ENV_VAR,
                metadata={
                    "k8s_resource": k8s_id,
                    **source_info,
                },
            )
            
            yield Edge(
                source_id=k8s_id,
                target_id=env_id,
                type=RelationshipType.PROVIDES,
            )
            
            # Create edges to ConfigMaps/Secrets
            if env_var.is_config_map_ref and env_var.config_map_name:
                cm_id = f"k8s:{namespace}/configmap/{env_var.config_map_name}"
                yield Edge(
                    source_id=env_id,
                    target_id=cm_id,
                    type=RelationshipType.READS,
                    metadata={"key": env_var.config_map_key},
                )
            
            if env_var.is_secret_ref and env_var.secret_name:
                secret_id = f"k8s:{namespace}/secret/{env_var.secret_name}"
                yield Edge(
                    source_id=env_id,
                    target_id=secret_id,
                    type=RelationshipType.READS,
                    metadata={"key": env_var.secret_key},
                )
        
        # Create edges to referenced ConfigMaps
        for cm_name in config_maps:
            if cm_name:
                cm_id = f"k8s:{namespace}/configmap/{cm_name}"
                yield Edge(
                    source_id=k8s_id,
                    target_id=cm_id,
                    type=RelationshipType.READS,
                )
        
        # Create edges to referenced Secrets
        for secret_name in secrets:
            if secret_name:
                secret_id = f"k8s:{namespace}/secret/{secret_name}"
                yield Edge(
                    source_id=k8s_id,
                    target_id=secret_id,
                    type=RelationshipType.READS,
                )
        
        # Create edge to ServiceAccount if specified
        if service_account:
            sa_id = f"k8s:{namespace}/serviceaccount/{service_account}"
            yield Edge(
                source_id=k8s_id,
                target_id=sa_id,
                type=RelationshipType.CONFIGURES,
            )
    
    def _get_pod_spec(self, doc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract the PodSpec from various workload types.
        
        Different K8s resources have the pod spec at different paths.
        """
        kind = doc.get("kind", "")
        spec = doc.get("spec", {})
        
        if kind == "Pod":
            return spec
        
        elif kind in ("Deployment", "ReplicaSet", "DaemonSet", "StatefulSet"):
            template = spec.get("template", {})
            return template.get("spec", {})
        
        elif kind == "Job":
            template = spec.get("template", {})
            return template.get("spec", {})
        
        elif kind == "CronJob":
            job_template = spec.get("jobTemplate", {})
            job_spec = job_template.get("spec", {})
            template = job_spec.get("template", {})
            return template.get("spec", {})
        
        return None
    
    def _extract_env_vars(self, env_list: List[Dict[str, Any]]) -> List[K8sEnvVar]:
        """Extract environment variables from a container's env spec."""
        result: List[K8sEnvVar] = []
        
        for env in env_list:
            name = env.get("name", "")
            if not name:
                continue
            
            env_var = K8sEnvVar(name=name)
            
            # Direct value
            if "value" in env:
                env_var.value = env["value"]
            
            # ValueFrom reference
            elif "valueFrom" in env:
                value_from = env["valueFrom"]
                
                # ConfigMap reference
                if "configMapKeyRef" in value_from:
                    ref = value_from["configMapKeyRef"]
                    env_var.config_map_name = ref.get("name")
                    env_var.config_map_key = ref.get("key")
                
                # Secret reference
                elif "secretKeyRef" in value_from:
                    ref = value_from["secretKeyRef"]
                    env_var.secret_name = ref.get("name")
                    env_var.secret_key = ref.get("key")
                
                # Field reference (e.g., metadata.name)
                elif "fieldRef" in value_from:
                    ref = value_from["fieldRef"]
                    env_var.field_ref = ref.get("fieldPath")
                
                # Resource field reference
                elif "resourceFieldRef" in value_from:
                    ref = value_from["resourceFieldRef"]
                    env_var.field_ref = f"resource:{ref.get('resource')}"
            
            result.append(env_var)
        
        return result
    
    def extract_resources(self, manifest_path: Path) -> List[K8sResource]:
        """
        Extract all K8s resources as typed objects.
        
        Convenience method for getting structured resource data.
        """
        resources: List[K8sResource] = []
        
        if not YAML_AVAILABLE:
            return resources
        
        try:
            content = manifest_path.read_text()
            documents = list(yaml.safe_load_all(content))
        except Exception as e:
            self._logger.error(f"Failed to parse manifest: {e}")
            return resources
        
        for doc in documents:
            if not doc or not isinstance(doc, dict):
                continue
            
            kind = doc.get("kind", "")
            if not kind:
                continue
            
            metadata = doc.get("metadata", {})
            name = metadata.get("name", "")
            namespace = metadata.get("namespace", "default")
            api_version = doc.get("apiVersion", "")
            
            # Extract workload-specific info
            env_vars: List[K8sEnvVar] = []
            config_maps: List[str] = []
            secrets: List[str] = []
            images: List[str] = []
            service_account: Optional[str] = None
            volumes: List[Dict[str, Any]] = []
            
            if kind in self.WORKLOAD_KINDS:
                pod_spec = self._get_pod_spec(doc)
                if pod_spec:
                    service_account = pod_spec.get("serviceAccountName")
                    volumes = pod_spec.get("volumes", [])
                    
                    for container in pod_spec.get("containers", []):
                        if container.get("image"):
                            images.append(container["image"])
                        env_vars.extend(
                            self._extract_env_vars(container.get("env", []))
                        )
                        
                        for env_from in container.get("envFrom", []):
                            if "configMapRef" in env_from:
                                config_maps.append(
                                    env_from["configMapRef"].get("name", "")
                                )
                            if "secretRef" in env_from:
                                secrets.append(
                                    env_from["secretRef"].get("name", "")
                                )
            
            resources.append(K8sResource(
                kind=kind,
                name=name,
                namespace=namespace,
                api_version=api_version,
                labels=metadata.get("labels", {}),
                annotations=metadata.get("annotations", {}),
                env_vars=env_vars,
                config_maps=config_maps,
                secrets=secrets,
                images=images,
                service_account=service_account,
                volumes=volumes,
            ))
        
        return resources


def create_kubernetes_parser(context: Optional[ParserContext] = None) -> KubernetesParser:
    """Factory function to create a Kubernetes parser."""
    return KubernetesParser(context)