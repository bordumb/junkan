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

import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    
    Attributes:
        id: Unique identifier (e.g., "env:DB_HOST", "infra:aws_db_instance.main")
        name: Human-readable name
        type: Category from NodeType enum
        path: File path where this node was discovered
        language: Source language (python, terraform, kubernetes, etc.)
        file_hash: Hash of source file for incremental scanning
        tokens: Tokenized name for fuzzy matching
        metadata: Extensible key-value storage for parser-specific data
        created_at: Timestamp of node creation
    """
    id: str
    name: str
    type: NodeType
    path: Optional[str] = None
    language: Optional[str] = None
    file_hash: Optional[str] = None
    tokens: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def model_post_init(self, __context) -> None:
        """Generate tokens from name if not provided."""
        if not self.tokens and self.name:
            object.__setattr__(self, 'tokens', self._tokenize(self.name))

    @staticmethod
    def _tokenize(name: str) -> List[str]:
        """
        Split name into normalized tokens for matching.
        
        Handles common naming conventions across languages:
        - SCREAMING_SNAKE_CASE (env vars)
        - snake_case (Python, Terraform)
        - kebab-case (Kubernetes)
        - dot.notation (Java packages, Terraform resources)
        - path/separators (file paths)
        
        Examples:
            "PAYMENT_DB_HOST" -> ["payment", "db", "host"]
            "aws_db_instance.main" -> ["aws", "db", "instance", "main"]
            "my-kubernetes-service" -> ["my", "kubernetes", "service"]
        """
        normalized = name.lower()
        for sep in ["_", ".", "-", "/", ":"]:
            normalized = normalized.replace(sep, " ")
        return [t.strip() for t in normalized.split() if t.strip()]

    def with_metadata(self, **kwargs) -> "Node":
        """
        Return a new Node with additional metadata merged in.
        
        Useful for adding parser-specific data without mutation.
        
        Example:
            node = node.with_metadata(line_number=42, column=10)
        """
        merged = {**self.metadata, **kwargs}
        return self.model_copy(update={"metadata": merged})

    def matches_tokens(self, other_tokens: List[str], min_overlap: int = 2) -> bool:
        """
        Check if this node's tokens overlap sufficiently with another set.
        
        Args:
            other_tokens: Tokens to compare against
            min_overlap: Minimum number of shared tokens required
            
        Returns:
            True if overlap meets threshold
        """
        overlap = set(self.tokens) & set(other_tokens)
        return len(overlap) >= min_overlap

    class Config:
        frozen = True


class Edge(BaseModel):
    """
    Directed relationship between two Nodes.
    
    Represents a dependency: source_id depends on or references target_id.
    The direction convention is:
    - source_id: The node that HAS the dependency
    - target_id: The node that IS the dependency
    
    Example: If Python code reads an env var, the edge is:
        source_id="file://app.py" -> target_id="env:DB_HOST"
        type=READS
        
    For infrastructure providing values:
        source_id="infra:db_host_output" -> target_id="env:DB_HOST"
        type=PROVIDES
    
    Attributes:
        source_id: ID of the source node
        target_id: ID of the target node  
        type: Relationship category from RelationshipType
        confidence: Match confidence score (0.0-1.0)
        match_strategy: How this edge was discovered (for stitched edges)
        metadata: Additional context (matched_tokens, explanation, rule name)
        created_at: Timestamp of edge creation
    """
    source_id: str
    target_id: str
    type: RelationshipType
    confidence: float = 1.0
    match_strategy: Optional[MatchStrategy] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def is_high_confidence(self, threshold: float = 0.8) -> bool:
        """Check if this edge meets high confidence threshold."""
        return self.confidence >= threshold

    def is_stitched(self) -> bool:
        """Check if this edge was created by stitching (vs direct parsing)."""
        return self.match_strategy is not None

    def get_matched_tokens(self) -> List[str]:
        """Extract matched tokens from metadata if present."""
        return self.metadata.get("matched_tokens", [])

    def get_explanation(self) -> str:
        """Extract explanation from metadata if present."""
        return self.metadata.get("explanation", "")

    def get_rule_name(self) -> Optional[str]:
        """Extract the stitching rule name that created this edge."""
        return self.metadata.get("rule")


class MatchResult(BaseModel):
    """
    Result of a stitching match attempt.
    
    Captures details about why two nodes were linked, enabling
    explainability and debugging of the matching process.
    
    Attributes:
        source_node: ID of the source node
        target_node: ID of the target node
        strategy: Which matching strategy succeeded
        confidence: Calculated confidence score
        matched_tokens: Which tokens contributed to the match
        explanation: Human-readable description of why this matched
    """
    source_node: str
    target_node: str
    strategy: MatchStrategy
    confidence: float
    matched_tokens: List[str] = Field(default_factory=list)
    explanation: str = ""

    def to_edge(self, relationship_type: RelationshipType, rule_name: str = "") -> Edge:
        """
        Convert this match result to an Edge.
        
        Args:
            relationship_type: The type of relationship this represents
            rule_name: Name of the stitching rule that created this match
            
        Returns:
            An Edge instance with metadata populated from this result
        """
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
        
        Used when multiple potential matches exist for the same source.
        """
        if self.confidence != other.confidence:
            return self.confidence > other.confidence
        # Tie-breaker: prefer more matched tokens
        return len(self.matched_tokens) > len(other.matched_tokens)


class ScanMetadata(BaseModel):
    """
    Metadata for tracking file state in incremental scanning.
    
    Enables jnkn to skip unchanged files on subsequent scans,
    dramatically improving performance for large codebases.
    
    Attributes:
        file_path: Absolute or relative path to the file
        file_hash: Hash of file contents for change detection
        last_scanned: When this file was last processed
        node_count: Number of nodes extracted from this file
        edge_count: Number of edges extracted from this file
    """
    file_path: str
    file_hash: str
    last_scanned: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))    
    node_count: int = 0
    edge_count: int = 0

    @staticmethod
    def compute_hash(file_path: str) -> str:
        """
        Compute hash of file contents for change detection.
        
        Uses xxhash for speed if available, falls back to MD5.
        
        Args:
            file_path: Path to the file to hash
            
        Returns:
            Hex digest of file contents, or empty string on error
        """
        try:
            import xxhash
            with open(file_path, "rb") as f:
                return xxhash.xxh64(f.read()).hexdigest()
        except ImportError:
            # Fallback to MD5 if xxhash not installed
            with open(file_path, "rb") as f:
                return hashlib.md5(f.read()).hexdigest()
        except Exception:
            # File doesn't exist or can't be read
            return ""

    def is_stale(self, current_hash: str) -> bool:
        """
        Check if the file has changed since last scan.
        
        Args:
            current_hash: Hash of current file contents
            
        Returns:
            True if file has changed and needs re-scanning
        """
        return self.file_hash != current_hash

    @classmethod
    def from_file(cls, file_path: str, node_count: int = 0, edge_count: int = 0) -> "ScanMetadata":
        """
        Create ScanMetadata from a file path.
        
        Convenience method that computes the hash automatically.
        
        Args:
            file_path: Path to the file
            node_count: Number of nodes extracted
            edge_count: Number of edges extracted
            
        Returns:
            ScanMetadata instance with computed hash
        """
        return cls(
            file_path=file_path,
            file_hash=cls.compute_hash(file_path),
            node_count=node_count,
            edge_count=edge_count,
        )


class SchemaVersion(BaseModel):
    """
    Database schema version for migrations.
    
    Stored in the schema_version table to track which migrations
    have been applied to the SQLite database.
    
    Attributes:
        version: Integer version number (monotonically increasing)
        applied_at: When this migration was applied
        description: Human-readable description of what changed
    """
    version: int
    applied_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str = ""
