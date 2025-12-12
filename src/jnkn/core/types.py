"""
Core type definitions for jnkn.

Refactored to use Domain-Specific TypedDicts for metadata.
This structure maps cleanly to Rust enums (Sum Types) while maintaining
Python flexibility via Union types.
"""

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, NotRequired, TypedDict, Union

from pydantic import BaseModel, ConfigDict, Field


class NodeType(StrEnum):
    """Categories of nodes in the dependency graph."""
    CODE_FILE = "code_file"
    CODE_ENTITY = "code_entity"
    INFRA_RESOURCE = "infra_resource"
    INFRA_MODULE = "infra_module"
    DATA_ASSET = "data_asset"
    ENV_VAR = "env_var"
    CONFIG_KEY = "config_key"
    SECRET = "secret"
    JOB = "job"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    """Types of relationships between nodes."""
    CONTAINS = "contains"
    IMPORTS = "imports"
    EXTENDS = "extends"
    CALLS = "calls"
    READS = "reads"
    WRITES = "writes"
    PROVISIONS = "provisions"
    CONFIGURES = "configures"
    DEPENDS_ON = "depends_on"
    PROVIDES = "provides"
    CONSUMES = "consumes"
    TRANSFORMS = "transforms"
    ROUTES_TO = "routes_to"


class MatchStrategy(StrEnum):
    """Strategies used for fuzzy matching in stitching."""
    EXACT = "exact"
    NORMALIZED = "normalized"
    TOKEN_OVERLAP = "token_overlap"
    SUFFIX = "suffix"
    PREFIX = "prefix"
    CONTAINS = "contains"
    SEMANTIC = "semantic"


# =============================================================================
# Domain-Specific Metadata Schemas
# =============================================================================

class BaseMeta(TypedDict, total=False):
    """Common metadata fields across all node types."""
    language: NotRequired[str]
    source: NotRequired[str]
    file: NotRequired[str]
    line: NotRequired[int]
    lines: NotRequired[int]
    column: NotRequired[int]
    parser: NotRequired[str]
    confidence: NotRequired[float]
    virtual: NotRequired[bool]
    inferred: NotRequired[bool]


class PythonMeta(BaseMeta, total=False):
    """Metadata specific to Python nodes."""
    entity_type: NotRequired[str]
    decorators: NotRequired[List[str]]


class TerraformMeta(BaseMeta, total=False):
    """Metadata specific to Terraform nodes."""
    terraform_type: NotRequired[str]
    terraform_address: NotRequired[str]
    change_actions: NotRequired[List[str]]
    is_local: NotRequired[bool]
    is_data: NotRequired[bool]


class KubernetesMeta(BaseMeta, total=False):
    """Metadata specific to Kubernetes nodes."""
    k8s_kind: NotRequired[str]
    k8s_api_version: NotRequired[str]
    k8s_resource: NotRequired[str]
    namespace: NotRequired[str]


class DbtMeta(BaseMeta, total=False):
    """Metadata specific to dbt nodes."""
    dbt_unique_id: NotRequired[str]
    schema: NotRequired[str]
    database: NotRequired[str]
    package: NotRequired[str]
    resource_type: NotRequired[str]
    description: NotRequired[str]
    tags: NotRequired[List[str]]
    materialized: NotRequired[str]


class SparkMeta(BaseMeta, total=False):
    """Metadata specific to Spark/OpenLineage nodes."""
    source_type: NotRequired[str]
    pattern: NotRequired[str]
    default_value: NotRequired[str]


class JsMeta(BaseMeta, total=False):
    """Metadata specific to JavaScript/TypeScript nodes."""
    framework: NotRequired[str]
    is_public: NotRequired[bool]
    is_commonjs: NotRequired[bool]
    is_dynamic: NotRequired[bool]
    import_name: NotRequired[str]


# The Master Metadata Union
# Maps to a Rust Enum: NodeMetadata::Python(PythonMeta), NodeMetadata::Generic(Map), etc.
# Including Dict[str, Any] at the end allows for unknown parsers without validation errors.
NodeMetadata = Union[
    PythonMeta,
    TerraformMeta,
    KubernetesMeta,
    DbtMeta,
    SparkMeta,
    JsMeta,
    Dict[str, Any]
]


# =============================================================================
# Core Models
# =============================================================================

class Node(BaseModel):
    """
    Universal Unit of Analysis.
    """
    id: str
    name: str
    type: NodeType
    path: str | None = None
    language: str | None = None
    file_hash: str | None = None
    tokens: List[str] = Field(default_factory=list)
    
    # Use the Union type for structured + flexible metadata
    metadata: NodeMetadata = Field(default_factory=dict)
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = ConfigDict(frozen=False, extra='allow')

    def model_post_init(self, __context) -> None:
        if not self.tokens and self.name:
            object.__setattr__(self, 'tokens', self._tokenize(self.name))

    @staticmethod
    def _tokenize(name: str) -> List[str]:
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]

    def with_metadata(self, **kwargs) -> "Node":
        merged = {**self.metadata, **kwargs}
        return self.model_copy(update={"metadata": merged})

    def __hash__(self):
        return hash(self.id)

    def __eq__(self, other):
        if isinstance(other, Node):
            return self.id == other.id
        return False


class Edge(BaseModel):
    """
    Directed relationship between two Nodes.
    """
    source_id: str
    target_id: str
    type: RelationshipType
    confidence: float = 1.0
    match_strategy: MatchStrategy | None = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if this edge meets high confidence threshold."""
        return self.confidence >= threshold

    def is_stitched(self) -> bool:
        return self.match_strategy is not None

    def get_matched_tokens(self) -> List[str]:
        """Extract matched tokens from metadata if present."""
        return self.metadata.get("matched_tokens", [])

    def get_explanation(self) -> str:
        """Extract explanation from metadata if present."""
        return self.metadata.get("explanation", "")

    def get_rule_name(self) -> str | None:
        """Extract the stitching rule name that created this edge."""
        return self.metadata.get("rule")


class MatchResult(BaseModel):
    """
    Result of a stitching match attempt.
    """
    source_node: str
    target_node: str
    strategy: MatchStrategy
    confidence: float
    matched_tokens: List[str] = Field(default_factory=list)
    explanation: str = ""

    def to_edge(self, relationship_type: RelationshipType, rule_name: str = "") -> Edge:
        return Edge(
            source_id=self.source_node,
            target_id=self.target_node,
            type=relationship_type,
            confidence=self.confidence,
            match_strategy=self.strategy,
            metadata={
                "matched_tokens": self.matched_tokens,
                "explanation": self.explanation,
                "rule": rule_name,
            }
        )

    def is_better_than(self, other: "MatchResult") -> bool:
        """
        Compare two match results to determine which is stronger.
        """
        if self.confidence != other.confidence:
            return self.confidence > other.confidence
        # Tie-breaker: prefer more matched tokens
        return len(self.matched_tokens) > len(other.matched_tokens)


class ScanMetadata(BaseModel):
    """
    Metadata for tracking file state in incremental scanning.
    """
    file_path: str
    file_hash: str
    last_scanned: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))    
    node_count: int = 0
    edge_count: int = 0

    @staticmethod
    def compute_hash(file_path: str) -> str:
        try:
            import xxhash
            with open(file_path, "rb") as f:
                return xxhash.xxh64(f.read()).hexdigest()
        except ImportError:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""

    def is_stale(self, current_hash: str) -> bool:
        return self.file_hash != current_hash

    @classmethod
    def from_file(cls, file_path: str, node_count: int = 0, edge_count: int = 0) -> "ScanMetadata":
        return cls(
            file_path=file_path,
            file_hash=cls.compute_hash(file_path),
            node_count=node_count,
            edge_count=edge_count,
        )


class SchemaVersion(BaseModel):
    """
    Database schema version for migrations.
    """
    version: int
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""