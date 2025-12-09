"""
Storage adapters for jnkn.

Provides pluggable persistence backends:
- SQLiteStorage: Production-ready local persistence
- MemoryStorage: Fast ephemeral storage for testing
"""

from .base import StorageAdapter
from .sqlite import SQLiteStorage
from .memory import MemoryStorage

__all__ = ["StorageAdapter", "SQLiteStorage", "MemoryStorage"]