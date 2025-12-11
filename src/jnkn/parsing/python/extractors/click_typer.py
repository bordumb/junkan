import re
from pathlib import Path
from typing import Generator, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree


class ClickTyperExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "click_typer"

    @property
    def priority(self) -> int:
        return 80

    def can_extract(self, text: str) -> bool:
        return "click" in text or "typer" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Tree | None,
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:

        # Regex for @click.option(..., envvar='VAR') or envvar=['VAR', 'VAR2']
        # Added re.DOTALL to handle multiline decorators
        click_pattern = re.compile(
            r'(?:@click\.option|typer\.Option)\s*\([^)]*envvar\s*=\s*(\[[^\]]+\]|["\'][^"\']+["\'])',
            re.DOTALL
        )

        for match in click_pattern.finditer(text):
            envvar_val = match.group(1)

            # Extract string literals from list or single string
            vars_found = re.findall(r'["\']([^"\']+)["\']', envvar_val)

            line = text[:match.start()].count('\n') + 1

            for var_name in vars_found:
                if not is_valid_env_var_name(var_name):
                    continue

                if var_name in seen_vars:
                    continue

                env_id = f"env:{var_name}"

                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "click_typer",
                        "file": str(file_path),
                        "line": line,
                    },
                )

                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": "click_typer", "line": line},
                )
