from dataclasses import dataclass
from typing import List


@dataclass
class PythonEnvVar:
    """Represents a detected environment variable usage."""

    name: str
    pattern: str  # Which pattern detected it
    line: int
    column: int
    default_value: str | None = None

    def to_node_id(self) -> str:
        return f"env:{self.name}"


@dataclass
class PythonImport:
    """Represents an import statement."""

    module: str
    is_from_import: bool
    is_relative: bool
    line: int
    names: List[str] = None  # For 'from x import a, b, c'

    def to_file_path(self) -> str:
        """Convert import to a probable file path."""
        if self.is_relative:
            return self.module
        return self.module.replace(".", "/") + ".py"


@dataclass
class PythonDefinition:
    """Represents a function or class definition."""

    name: str
    kind: str  # "function" or "class"
    line: int
    decorators: List[str] = None

    def to_node_id(self, file_path: str) -> str:
        return f"entity:{file_path}:{self.name}"
