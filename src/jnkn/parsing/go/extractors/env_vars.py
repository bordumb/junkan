import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class GoEnvVarExtractor:
    """
    Extract environment variable reads from Go code.

    Supports:
    - os.Getenv("VAR")
    - os.LookupEnv("VAR")
    - syscall.Getenv("VAR")
    - viper.GetString("key") (often mapped to env vars)
    """

    name = "go_env_vars"
    priority = 100

    # os.Getenv("VAR")
    GETENV = re.compile(r'(?:os|syscall)\.Getenv\s*\(\s*"([^"]+)"\s*\)')

    # os.LookupEnv("VAR")
    LOOKUPENV = re.compile(r'os\.LookupEnv\s*\(\s*"([^"]+)"\s*\)')

    # viper.GetString("key") - commonly used for config which can be env vars
    VIPER = re.compile(r'viper\.Get(?:String|Int|Bool|Float64|Duration)\s*\(\s*"([^"]+)"\s*\)')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "os." in ctx.text or "syscall." in ctx.text or "viper." in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        seen = set()

        for pattern, source in [
            (self.GETENV, "os.Getenv"),
            (self.LOOKUPENV, "os.LookupEnv"),
            (self.VIPER, "viper"),
        ]:
            for match in pattern.finditer(ctx.text):
                var_name = match.group(1)

                # Basic validation
                if not var_name or " " in var_name:
                    continue

                if var_name in seen:
                    continue
                seen.add(var_name)

                line = ctx.text[: match.start()].count("\n") + 1

                # For viper, keys are often lowercase but map to UPPERCASE env vars
                # We'll store the exact key, but stitcher logic might need to handle case
                env_id = f"env:{var_name}"

                yield Node(
                    id=env_id,
                    name=var_name,
                    type=NodeType.ENV_VAR,
                    path=str(ctx.file_path),
                    metadata={"source": source, "line": line, "is_config_key": source == "viper"},
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"pattern": source},
                )
