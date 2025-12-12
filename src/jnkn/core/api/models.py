"""
Strict API Models for CLI Output.

These Pydantic models define the immutable contract between the CLI
and external consumers (like the VS Code extension).
"""

from typing import List

from pydantic import BaseModel, Field


class BreakdownStats(BaseModel):
    """Counts of impacted artifacts by domain."""

    code: List[str] = Field(default_factory=list)
    infra: List[str] = Field(default_factory=list)
    data: List[str] = Field(default_factory=list)
    config: List[str] = Field(default_factory=list)
    other: List[str] = Field(default_factory=list)


class BlastRadiusResponse(BaseModel):
    """
    Schema for 'jnkn blast' JSON output.
    VS Code extension relies on this exact structure.
    """

    source_artifacts: List[str]
    impacted_artifacts: List[str]
    count: int
    breakdown: BreakdownStats


class ScanSummary(BaseModel):
    """
    Schema for 'jnkn scan' JSON output.
    """

    total_files: int
    files_parsed: int
    files_skipped: int
    nodes_found: int
    edges_found: int
    new_links_stitched: int
    output_path: str
    duration_sec: float
