import re
from pathlib import Path
from typing import Generator, Optional, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from .base import BaseExtractor, Tree


class HeuristicExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "heuristic"

    @property
    def priority(self) -> int:
        return 10

    def can_extract(self, text: str) -> bool:
        return True # Runs on everything as a fallback

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Optional[Tree],
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:

        # Pattern: VAR_NAME = ... where VAR_NAME suggests an env var
        # FIX: Restricted to UPPERCASE start to avoid local variable false positives (e.g. db_host)
        env_like_assignment = re.compile(
            r'^([A-Z][A-Z0-9_]*(?:_URL|_HOST|_PORT|_KEY|_SECRET|_TOKEN|_PASSWORD|_USER|_PATH|_DIR|_ENDPOINT|_URI|_DSN|_CONN))\s*=',
            re.MULTILINE
        )

        for match in env_like_assignment.finditer(text):
            var_name = match.group(1)

            if var_name in seen_vars:
                continue

            # Context check
            line_start = text.rfind('\n', 0, match.start()) + 1
            line_end = text.find('\n', match.end())
            if line_end == -1:
                line_end = len(text)
            line_content = text[line_start:line_end]

            env_indicators = [
                'os.getenv', 'os.environ', 'getenv', 'environ',
                'config', 'settings', 'env', 'ENV',
            ]

            if not any(ind in line_content for ind in env_indicators):
                continue

            line = text[:match.start()].count('\n') + 1
            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "heuristic",
                    "file": str(file_path),
                    "line": line,
                    "confidence": 0.7,
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "heuristic", "confidence": 0.7, "line": line},
            )
