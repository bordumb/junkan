import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from .base import BaseExtractor, ExtractionContext


class HeuristicExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "heuristic"

    @property
    def priority(self) -> int:
        return 10

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return True

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        env_like_assignment = re.compile(
            r"^([A-Z][A-Z0-9_]*(?:_URL|_HOST|_PORT|_KEY|_SECRET|_TOKEN|_PASSWORD|_USER|_PATH|_DIR|_ENDPOINT|_URI|_DSN|_CONN))\s*=",
            re.MULTILINE,
        )

        for match in env_like_assignment.finditer(ctx.text):
            var_name = match.group(1)

            if var_name in ctx.seen_ids:
                continue

            line_start = ctx.text.rfind("\n", 0, match.start()) + 1
            line_end = ctx.text.find("\n", match.end())
            if line_end == -1:
                line_end = len(ctx.text)
            line_content = ctx.text[line_start:line_end]

            env_indicators = [
                "os.getenv",
                "os.environ",
                "getenv",
                "environ",
                "config",
                "settings",
                "env",
                "ENV",
            ]

            if not any(ind in line_content for ind in env_indicators):
                continue

            ctx.seen_ids.add(var_name)

            line = ctx.text[: match.start()].count("\n") + 1
            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "heuristic",
                    "file": str(ctx.file_path),
                    "line": line,
                    "confidence": 0.7,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "heuristic", "confidence": 0.7, "line": line},
            )
