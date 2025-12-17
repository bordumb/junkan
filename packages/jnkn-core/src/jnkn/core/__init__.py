"""
jnkn Core Module.

This package contains the fundamental building blocks for dependency
analysis and multi-repository support:

Core Types & Graph:
    - Node, Edge: Graph data structures
    - DependencyGraph: In-memory dependency graph
    - ConfidenceCalculator: Confidence scoring engine

Multi-Repository Support:
    Phase 1 - Local Dependencies:
        - ProjectManifest: Parse jnkn.toml configuration
        - DependencyResolver: Resolve local path dependencies

    Phase 2 - Git Remote Dependencies:
        - GitFetcher: Clone and cache git repositories
        - Lockfile: Pin git dependencies to specific SHAs
        - CacheManager: Manage the dependency cache

    Phase 3 - Explicit Mappings:
        - ExplicitMapping: User-defined artifact mappings
        - MappingMatcher: Pattern matching for mappings
        - EnhancedStitcher: Stitching with mapping integration
"""

# Original core exports
from .cache import (
    CacheItem,
    CacheManager,
    CacheStats,
    format_cache_list,
    get_cache_dir,
)
from .confidence import (
    ConfidenceCalculator,
    ConfidenceConfig,
    ConfidenceResult,
    ConfidenceSignal,
    PenaltyType,
    create_default_calculator,
)
from .enhanced_stitching import (
    EnhancedStitcher,
    StitchingResult,
    create_enhanced_stitcher,
)
from .git_fetcher import (
    CacheEntry,
    GitFetcher,
    GitFetchError,
)
from .graph import DependencyGraph, TokenIndex

# Phase 2: Git & Lockfile
from .lockfile import (
    LockedPackage,
    Lockfile,
    create_locked_package,
)

# Phase 1: Manifest & Local Dependencies
from .manifest import (
    DependencySource,
    DependencySpec,
    ExplicitMapping,
    GitSpec,
    MappingType,
    ProjectManifest,
    ResolvedDependency,
    ToolJnknConfig,
)

# Phase 3: Explicit Mappings
from .mappings import (
    MappingMatch,
    MappingMatcher,
    MappingValidationWarning,
    MappingValidator,
    load_mappings_from_manifest,
    suggest_mappings,
)
from .resolver import (
    DependencyError,
    DependencyResolver,
    ResolutionResult,
    resolve_dependencies,
    update_lockfile,
)
from .types import Edge, MatchResult, MatchStrategy, Node, NodeType, RelationshipType, ScanMetadata

__all__ = [
    # Types
    "Node",
    "Edge",
    "NodeType",
    "RelationshipType",
    "MatchStrategy",
    "MatchResult",
    "ScanMetadata",
    # Graph
    "DependencyGraph",
    "TokenIndex",
    # Confidence
    "ConfidenceCalculator",
    "ConfidenceConfig",
    "ConfidenceResult",
    "ConfidenceSignal",
    "PenaltyType",
    "create_default_calculator",
    # Phase 1: Manifest & Local Dependencies
    "DependencySource",
    "DependencySpec",
    "GitSpec",
    "ProjectManifest",
    "ResolvedDependency",
    "ToolJnknConfig",
    "DependencyError",
    "DependencyResolver",
    "ResolutionResult",
    "resolve_dependencies",
    # Phase 2: Git & Lockfile
    "GitFetcher",
    "GitFetchError",
    "CacheEntry",
    "Lockfile",
    "LockedPackage",
    "create_locked_package",
    "update_lockfile",
    "CacheItem",
    "CacheManager",
    "CacheStats",
    "format_cache_list",
    "get_cache_dir",
    # Phase 3: Explicit Mappings
    "ExplicitMapping",
    "MappingType",
    "MappingMatch",
    "MappingMatcher",
    "MappingValidationWarning",
    "MappingValidator",
    "load_mappings_from_manifest",
    "suggest_mappings",
    # Enhanced Stitching
    "EnhancedStitcher",
    "StitchingResult",
    "create_enhanced_stitcher",
]
