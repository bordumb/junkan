import re
from pathlib import Path
from typing import Generator, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree

# Regex patterns for fallback parsing
ENV_VAR_PATTERNS = [
    # os.getenv("VAR") or os.getenv('VAR')
    (r'os\.getenv\s*\(\s*["\']([^"\']+)["\']', "os.getenv"),
    # os.environ.get("VAR")
    (r'os\.environ\.get\s*\(\s*["\']([^"\']+)["\']', "os.environ.get"),
    # os.environ["VAR"]
    (r'os\.environ\s*\[\s*["\']([^"\']+)["\']', "os.environ[]"),
    # environ.get("VAR") - after from import
    (r'(?<!os\.)environ\.get\s*\(\s*["\']([^"\']+)["\']', "environ.get"),
    # environ["VAR"] - after from import
    (r'(?<!os\.)environ\s*\[\s*["\']([^"\']+)["\']', "environ[]"),
    # getenv("VAR") - REMOVED redundant pattern that conflicted with os.getenv
    # if users do `from os import getenv`, the regex below captures it safely
    (r'(?<!os\.)getenv\s*\(\s*["\']([^"\']+)["\']', "getenv"),
]

class StdlibExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "stdlib"

    @property
    def priority(self) -> int:
        return 100

    def can_extract(self, text: str) -> bool:
        return "os." in text or "environ" in text or "getenv" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Tree | None,
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:

        for pattern, pattern_name in ENV_VAR_PATTERNS:
            regex = re.compile(pattern)

            for match in regex.finditer(text):
                var_name = match.group(1)

                # Filter out default values (false positive prevention)
                if not is_valid_env_var_name(var_name):
                    continue

                if var_name in seen_vars:
                    continue

                # Calculate line number
                line = text[:match.start()].count('\n') + 1

                env_id = f"env:{var_name}"

                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": pattern_name,
                        "file": str(file_path),
                        "line": line,
                    },
                )

                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": pattern_name, "line": line},
                )
