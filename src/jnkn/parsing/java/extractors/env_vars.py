import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class JavaEnvVarExtractor:
    """
    Extract environment variable reads and property injections from Java code.

    Supports:
    - System.getenv("VAR")
    - System.getProperty("prop")
    - Spring @Value("${VAR}") annotation
    - Spring Environment.getProperty("VAR")
    """

    name = "java_env_vars"
    priority = 100

    # System.getenv("VAR")
    GETENV = re.compile(r'System\.getenv\s*\(\s*"([^"]+)"\s*\)')

    # System.getProperty("prop")
    GETPROP = re.compile(r'System\.getProperty\s*\(\s*"([^"]+)"\s*\)')

    # @Value("${VAR}") or @Value("${VAR:default}")
    # Captures the content inside ${...}
    SPRING_VALUE = re.compile(r'@Value\s*\(\s*"\$\{\s*([^}]+)\s*\}\"\s*\)')

    # environment.getProperty("prop") - common variable name for Environment interface
    SPRING_ENV = re.compile(r'(?:env|environment)\.getProperty\s*\(\s*"([^"]+)"\s*\)')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "System.get" in ctx.text or "@Value" in ctx.text or "getProperty" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        seen = set()

        for pattern, source in [
            (self.GETENV, "System.getenv"),
            (self.GETPROP, "System.getProperty"),
            (self.SPRING_VALUE, "spring_value_annotation"),
            (self.SPRING_ENV, "spring_environment"),
        ]:
            for match in pattern.finditer(ctx.text):
                raw_var = match.group(1).strip()  # FIX: Strip whitespace

                # Handle Spring placeholders with defaults: ${VAR:default}
                if ":" in raw_var:
                    var_name = raw_var.split(":", 1)[0].strip()
                    default_value = raw_var.split(":", 1)[1].strip()
                else:
                    var_name = raw_var
                    default_value = None

                # Validate variable name (simple heuristic)
                # After stripping, if it still has spaces, it's likely not a valid env var
                if not var_name or " " in var_name:
                    continue

                if var_name in seen:
                    continue
                seen.add(var_name)

                line = ctx.text[: match.start()].count("\n") + 1
                env_id = f"env:{var_name}"

                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    path=str(ctx.file_path),
                    metadata={"source": source, "line": line, "default_value": default_value},
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": source},
                )
