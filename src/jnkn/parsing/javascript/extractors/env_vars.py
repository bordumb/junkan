"""
Environment Variable Extractor for JavaScript/TypeScript.
"""

import re
from typing import Generator, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class EnvVarExtractor:
    """
    Extract environment variables from JS/TS code.

    Handles:
    - process.env.VAR
    - process.env['VAR']
    - import.meta.env.VAR (Vite)
    - Destructuring: const { VAR } = process.env
    """

    name = "js_env_vars"
    priority = 100

    # Regex patterns
    PATTERNS = [
        (r"process\.env\.([A-Z][A-Z0-9_]*)", "process.env"),
        (r'process\.env\[["\']([^"\']+)["\']\]', "process.env[]"),
        (r"import\.meta\.env\.([A-Z][A-Z0-9_]*)", "import.meta.env"),
        # Destructuring: const { API_KEY, DB_HOST } = process.env
        (
            r"const\s*\{\s*([A-Z][A-Z0-9_]*(?:\s*,\s*[A-Z][A-Z0-9_]*)*)\s*\}\s*=\s*process\.env",
            "destructuring",
        ),
    ]

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "env" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        seen_vars: Set[str] = set()

        for pattern, source in self.PATTERNS:
            for match in re.finditer(pattern, ctx.text):
                # Handle comma-separated list from destructuring
                var_group = match.group(1)
                if "," in var_group:
                    vars_found = [v.strip() for v in var_group.split(",")]
                else:
                    vars_found = [var_group]

                for var_name in vars_found:
                    if var_name in seen_vars:
                        continue
                    seen_vars.add(var_name)

                    line = ctx.text[: match.start()].count("\n") + 1

                    # Detect framework/public status
                    framework = self._detect_framework(var_name)
                    is_public = var_name.startswith(("NEXT_PUBLIC_", "VITE_", "REACT_APP_"))

                    env_id = f"env:{var_name}"

                    yield Node(
                        id=env_id,
                        name=var_name,
                        type=NodeType.ENV_VAR,
                        path=str(ctx.file_path),
                        metadata={
                            "source": source,
                            "line": line,
                            "framework": framework,
                            "is_public": is_public,
                        },
                    )

                    yield Edge(
                        source_id=ctx.file_id,
                        target_id=env_id,
                        type=RelationshipType.READS,
                        metadata={"pattern": source},
                    )

    def _detect_framework(self, var_name: str) -> str | None:
        if var_name.startswith("NEXT_PUBLIC_") or var_name.startswith("NEXT_"):
            return "nextjs"
        elif var_name.startswith("VITE_"):
            return "vite"
        elif var_name.startswith("REACT_APP_"):
            return "create-react-app"
        return None
