import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, ExtractionContext


class PydanticExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "pydantic"

    @property
    def priority(self) -> int:
        return 90

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "BaseSettings" in ctx.text or "Field" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        # 1. Field(env="VAR") pattern
        field_env_pattern = r'Field\s*\([^)]*env\s*=\s*["\']([^"\']+)["\']'
        regex = re.compile(field_env_pattern, re.DOTALL)

        for match in regex.finditer(ctx.text):
            var_name = match.group(1)

            if not is_valid_env_var_name(var_name):
                continue

            if var_name in ctx.seen_ids:
                continue
            ctx.seen_ids.add(var_name)

            line = ctx.text[: match.start()].count("\n") + 1
            env_id = f"env:{var_name}"

            yield Node(
                id=env_id,
                name=var_name,
                type=NodeType.ENV_VAR,
                metadata={
                    "source": "pydantic_field",
                    "file": str(ctx.file_path),
                    "line": line,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "pydantic_field", "line": line},
            )

        # 2. BaseSettings class pattern
        class_pattern = re.compile(
            r"class\s+(\w+)\s*\([^)]*BaseSettings[^)]*\)\s*:\s*\n(.*?)(?=\nclass\s+\w+\s*[\(:]|\Z)",
            re.DOTALL,
        )

        for class_match in class_pattern.finditer(ctx.text):
            class_name = class_match.group(1)
            class_body = class_match.group(2)
            class_start_line = ctx.text[: class_match.start()].count("\n") + 1

            prefix = ""
            prefix_match = re.search(
                r'class\s+Config\s*:.*?env_prefix\s*=\s*["\']([^"\']*)["\']', class_body, re.DOTALL
            )
            if prefix_match:
                prefix = prefix_match.group(1)

            field_pattern = re.compile(r"^([ \t]{4}(\w+)\s*:\s*\w+.*?)$", re.MULTILINE)

            for field_match in field_pattern.finditer(class_body):
                field_line_content = field_match.group(1)
                field_name = field_match.group(2)

                if field_name.startswith("_") or field_name in (
                    "Config",
                    "model_config",
                    "model_fields",
                ):
                    continue

                if "Field" in field_line_content and "env=" in field_line_content:
                    continue

                env_var_name = prefix + field_name.upper()

                if env_var_name in ctx.seen_ids:
                    continue
                ctx.seen_ids.add(env_var_name)

                field_line = class_start_line + class_body[: field_match.start()].count("\n")
                env_id = f"env:{env_var_name}"

                yield Node(
                    id=env_id,
                    name=env_var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "pydantic_settings",
                        "file": str(ctx.file_path),
                        "line": field_line,
                        "settings_class": class_name,
                        "field_name": field_name,
                        "env_prefix": prefix,
                        "inferred": True,
                    },
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={
                        "pattern": "pydantic_settings",
                        "env_prefix": prefix,
                        "line": field_line,
                    },
                )
