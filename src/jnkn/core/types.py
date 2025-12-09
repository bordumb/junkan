"""
Core type definitions for jnkn.

This module defines the fundamental data structures used throughout the system:
- NodeType: Categories of nodes in the dependency graph
- RelationshipType: Types of edges between nodes
- Node: Represents any entity (file, resource, env var, etc.)
- Edge: Represents a directed relationship between nodes
- MatchResult: Captures stitching match details with confidence
- ScanMetadata: Tracks file state for incremental scanning
"""

from enum import StrEnum
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from datetime import datetime
import hashlib


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


class MatchStrategy(StrEnum):
    """Strategies used for fuzzy matching in stitching."""
    EXACT = "exact"
    NORMALIZED = "normalized"
    TOKEN_OVERLAP = "token_overlap"
    SUFFIX = "suffix"
    PREFIX = "prefix"
    CONTAINS = "contains"
    SEMANTIC = "semantic"


class Node(BaseModel):
    """
    Universal Unit of Analysis.
    
    Represents any entity in the dependency graph: files, functions,
    infrastructure resources, database tables, environment variables, etc.
    """
    id: str
    name: str
    type: NodeType
    path: Optional[str] = None
    language: Optional[str] = None
    file_hash: Optional[str] = None
    tokens: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    def model_post_init(self, __context) -> None:
        """Generate tokens from name if not provided."""
        if not self.tokens and self.name:
            object.__setattr__(self, 'tokens', self._tokenize(self.name))
    
    @staticmethod
    def _tokenize(name: str) -> List[str]:
        """
        Split name into normalized tokens for matching.
        
        Examples:
            "PAYMENT_DB_HOST" -> ["payment", "db", "host"]
            "aws_db_instance.main" -> ["aws", "db", "instance", "main"]
        """
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]
    
    class Config:
        frozen = True


class Edge(BaseModel):
    """
    Directed relationship between two Nodes.
    
    Represents a dependency: source_id depends on or references target_id.
    """
    source_id: str
    target_id: str
    type: RelationshipType
    confidence: float = 1.0
    match_strategy: Optional[MatchStrategy] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class MatchResult(BaseModel):
    """
    Result of a stitching match attempt.
    
    Captures details about why two nodes were linked.
    """
    source_node: str
    target_node: str
    strategy: MatchStrategy
    confidence: float
    matched_tokens: List[str] = Field(default_factory=list)
    explanation: str = ""


class ScanMetadata(BaseModel):
    """
    Metadata for tracking file state in incremental scanning.
    """
    file_path: str
    file_hash: str
    last_scanned: datetime = Field(default_factory=datetime.utcnow)
    node_count: int = 0
    edge_count: int = 0
    
    @staticmethod
    def compute_hash(file_path: str) -> str:
        """Compute hash of file contents for change detection."""
        try:
            import xxhash
            with open(file_path, "rb") as f:
                return xxhash.xxh64(f.read()).hexdigest()
        except ImportError:
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            return ""


class SchemaVersion(BaseModel):
    """Database schema version for migrations."""
    version: int
    applied_at: datetime = Field(default_factory=datetime.utcnow)
    description: str = ""