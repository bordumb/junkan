"""
FFI Protocols for Stitching Modules.

These interfaces define the boundary between Python and future Rust modules.
Using Protocols allows us to feature-flag the implementation (Python vs PyO3)
without changing the consuming code.
"""

from typing import List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class TokenMatcherProtocol(Protocol):
    """
    Protocol for token matching logic.
    Target for Rust migration via PyO3.
    """

    def tokenize(self, name: str) -> List[str]:
        """Split a name into normalized tokens."""
        ...

    def calculate_overlap(
        self, tokens1: List[str], tokens2: List[str]
    ) -> Tuple[List[str], float]:
        """Calculate token overlap and Jaccard score."""
        ...

    def get_significant_tokens(self, tokens: List[str]) -> List[str]:
        """Filter tokens based on configuration (stop words, length)."""
        ...
