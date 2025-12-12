import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, ExtractionContext

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
    # getenv("VAR")
    (r'(?<!os\.)getenv\s*\(\s*["\']([^"\']+)["\']', "getenv"),
]


class StdlibExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "stdlib"

    @property
    def priority(self) -> int:
        return 100

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "os." in ctx.text or "environ" in ctx.text or "getenv" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for pattern, pattern_name in ENV_VAR_PATTERNS:
            regex = re.compile(pattern)

            for match in regex.finditer(ctx.text):
                var_name = match.group(1)

                if not is_valid_env_var_name(var_name):
                    continue

                if var_name in ctx.seen_ids:
                    continue
                # We mark it seen so other extractors don't dup it
                # Note: ctx.seen_ids stores env var names here for coordination
                # Ideally, it should store Node IDs, but the python logic used names
                # We'll use names to maintain logic parity
                ctx.seen_ids.add(var_name)

                line = ctx.text[: match.start()].count("\n") + 1
                env_id = f"env:{var_name}"

                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": pattern_name,
                        "file": str(ctx.file_path),
                        "line": line,
                    },
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": pattern_name, "line": line},
                )
