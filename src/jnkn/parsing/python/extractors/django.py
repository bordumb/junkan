from pathlib import Path
from typing import Generator, Set, Union, Optional, Any
import re

from ....core.types import Node, Edge, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree, logger

class DjangoExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "django"

    @property
    def priority(self) -> int:
        return 60

    def can_extract(self, text: str) -> bool:
        return "environ" in text or "Env" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Optional[Tree],
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:
        
        # env("VAR"), env.str("VAR"), env.bool("VAR"), etc.
        # Matches env('VAR') or env.method('VAR')
        pattern = r'env(?:\.[a-zA-Z_]+)?\s*\(\s*["\']([^"\']+)["\']'
        regex = re.compile(pattern)
        
        for match in regex.finditer(text):
            var_name = match.group(1)
            
            if not is_valid_env_var_name(var_name):
                continue
                
            line = text[:match.start()].count('\n') + 1
            env_id = f"env:{var_name}"
            
            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "django_environ",
                    "file": str(file_path),
                    "line": line,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "django_environ", "line": line},
            )