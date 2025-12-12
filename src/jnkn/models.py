from enum import StrEnum
from typing import Any, Dict

from pydantic import BaseModel, Field


class RelationshipType(StrEnum):
    WRITES_TO = "writes_to"
    READS_FROM = "reads_from"
    TRANSFORMS = "transforms"
    CONFIGURES = "configures"
    DEPENDS_ON = "depends_on"
    TRIGGERS = "triggers"
    PROVIDES = "provides"
    CONSUMES = "consumes"


class ImpactRelationship(BaseModel):
    """Represents a dependency between two artifacts."""

    upstream_artifact: str
    downstream_artifact: str
    relationship_type: RelationshipType
    confidence: float = 1.0
    source: str = "manual"
    metadata: Dict[str, Any] = Field(default_factory=dict)
