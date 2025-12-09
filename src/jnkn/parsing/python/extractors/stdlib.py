from pathlib import Path
from typing import Generator, Set, Union, Optional, Any
import re

from ....core.types import Node, Edge, NodeType, RelationshipType
from ..models import PythonEnvVar
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree, logger

# Regex patterns for fallback parsing
ENV_VAR_PATTERNS = [
    # os.getenv("VAR") or os.getenv('VAR')
    (r'os\.getenv\s*\(\s*["\']([^"\']+)["\']', "os.getenv"),
    # os.environ.get("VAR")
    (r'os\.environ\.get\s*\(\s*["\']([^"\']+)["\']', "os.environ.get"),
    # os.environ["VAR"]
    (r'os\.environ\s*\[\s*["\']([^"\']+)["\']', "os.environ[]"),
    # getenv("VAR") - after from import
    (r'(?<!os\.)getenv\s*\(\s*["\']([^"\']+)["\']', "getenv"),
    # environ.get("VAR") - after from import
    (r'(?<!os\.)environ\.get\s*\(\s*["\']([^"\']+)["\']', "environ.get"),
    # environ["VAR"] - after from import
    (r'(?<!os\.)environ\s*\[\s*["\']([^"\']+)["\']', "environ[]"),
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
        tree: Optional[Tree],
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:
        
        # If tree-sitter is available, we could use it here. 
        # For this implementation, I am porting the robust regex logic from the original monolithic parser
        # as it was handling these patterns well. Tree-sitter query integration would go here.
        # Assuming we might want to prioritize tree-sitter in the future, structure allows it.
        
        for pattern, pattern_name in ENV_VAR_PATTERNS:
            regex = re.compile(pattern)
            
            for match in regex.finditer(text):
                var_name = match.group(1)
                
                # Filter out default values (false positive prevention)
                if not is_valid_env_var_name(var_name):
                    continue
                
                if var_name in seen_vars:
                    continue
                # Do NOT add to seen_vars here if you want multiple edges from same file to same env var?
                # Usually standard practice is one edge per file-var pair, but unique line numbers differ.
                # The 'seen_vars' passed in might be global for the file parsing session.
                # If we want to capture multiple usages, we might adjust logic.
                # For now, following original logic of deduplicating by name per file parse if desired, 
                # but 'seen_vars' is usually used to prevent duplicate NODES. 
                # Edges should probably be allowed if line numbers differ.
                # However, the prompt implies 'seen_vars' is to avoid duplicates.
                # I will adhere to the check.
                
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