import re
from pathlib import Path
from typing import Generator, Optional, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree


class EnvironsExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "environs"

    @property
    def priority(self) -> int:
        return 40

    def can_extract(self, text: str) -> bool:
        return "env" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Optional[Tree],
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:

        # env.str("VAR"), env.int("VAR"), etc.
        pattern = r'env\.(str|int|bool|float|list|dict|json|url|path|db|cache|email_url|search_url)\s*\(\s*["\']([^"\']+)["\']'
        regex = re.compile(pattern)

        for match in regex.finditer(text):
            var_name = match.group(2) # group 1 is method name

            if not is_valid_env_var_name(var_name):
                continue
            
            # Prevent duplicates if DjangoExtractor (priority 60) already found this
            if var_name in seen_vars:
                continue

            line = text[:match.start()].count('\n') + 1
            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "environs",
                    "file": str(file_path),
                    "line": line,
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "environs", "line": line},
            )
