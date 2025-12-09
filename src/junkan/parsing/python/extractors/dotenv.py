from pathlib import Path
from typing import Generator, Set, Union, Optional, Any
import re

from ....core.types import Node, Edge, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree, logger

class DotenvExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "dotenv"

    @property
    def priority(self) -> int:
        return 70

    def can_extract(self, text: str) -> bool:
        return "dotenv" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Optional[Tree],
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:
        
        # 1. Inline usage: dotenv_values(...)["VAR"]
        inline_pattern = r'dotenv_values\s*\([^)]*\)\s*\[\s*["\']([^"\']+)["\']'
        for match in re.finditer(inline_pattern, text):
            # FIX: Must use 'yield from' because _yield_match is a generator
            yield from self._yield_match(match, 1, text, file_path, file_id, "dotenv_values", seen_vars)

        # 2. Assignment tracking: config = dotenv_values(...)
        # Step A: Find variable names assigned to dotenv_values
        # Match: my_conf = dotenv_values(...)
        assignment_pattern = r'(\w+)\s*=\s*dotenv_values\s*\('
        config_vars = set()
        for match in re.finditer(assignment_pattern, text):
            config_vars.add(match.group(1))
        
        # Step B: Find usages of those variables: my_conf["VAR"] or my_conf.get("VAR")
        if config_vars:
            # Create regex for: var["KEY"] or var.get("KEY")
            # (?:var1|var2) ...
            vars_regex = "|".join(re.escape(v) for v in config_vars)
            
            # Match: config["VAR"]
            # FIX: Use raw f-string (rf) to handle backslashes correctly
            dict_access_pattern = rf'(?:{vars_regex})\s*\[\s*["\']([^"\']+)["\']'
            for match in re.finditer(dict_access_pattern, text):
                yield from self._yield_match(match, 1, text, file_path, file_id, "dotenv_values", seen_vars)

            # Match: config.get("VAR")
            # FIX: Use raw f-string (rf)
            get_access_pattern = rf'(?:{vars_regex})\.get\s*\(\s*["\']([^"\']+)["\']'
            for match in re.finditer(get_access_pattern, text):
                yield from self._yield_match(match, 1, text, file_path, file_id, "dotenv_values", seen_vars)

    def _yield_match(self, match, group_idx, text, file_path, file_id, pattern_name, seen_vars):
        var_name = match.group(group_idx)
        
        if not is_valid_env_var_name(var_name):
            return
            
        line = text[:match.start()].count('\n') + 1
        env_id = f"env:{var_name}"
        
        yield Node(
            id=env_id,
            name=var_name,
            type=NodeType.ENV_VAR,
            metadata={
                "source": "dotenv",
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