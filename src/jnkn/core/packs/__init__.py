"""
Framework Packs for Jnkn.

Framework Packs are pre-configured confidence settings and suppressions
optimized for specific technology stacks (e.g., Django + AWS, FastAPI + GCP).

They reduce false positives out-of-the-box and help users get value
from jnkn without manual tuning.
"""

from .loader import (
    FrameworkPack,
    PackLoader,
    apply_pack_to_config,
    detect_and_suggest_pack,
    get_available_packs,
    load_pack,
)

__all__ = [
    "FrameworkPack",
    "PackLoader",
    "get_available_packs",
    "load_pack",
    "detect_and_suggest_pack",
    "apply_pack_to_config",
]
