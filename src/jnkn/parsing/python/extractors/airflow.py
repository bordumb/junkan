import re
from pathlib import Path
from typing import Generator, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree


class AirflowExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "airflow"

    @property
    def priority(self) -> int:
        return 50

    def can_extract(self, text: str) -> bool:
        return "Variable" in text and "airflow" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Tree | None,
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:

        # Variable.get("VAR")
        pattern = r'Variable\.get\s*\(\s*["\']([^"\']+)["\']'
        regex = re.compile(pattern)

        for match in regex.finditer(text):
            var_name = match.group(1)

            if not is_valid_env_var_name(var_name):
                continue
            
            if var_name in seen_vars:
                continue

            line = text[:match.start()].count('\n') + 1
            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "airflow_variable",
                    "file": str(file_path),
                    "line": line,
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "airflow_variable", "line": line},
            )
