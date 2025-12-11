import re
from pathlib import Path
from typing import Generator, Set, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ..validation import is_valid_env_var_name
from .base import BaseExtractor, Tree


class PydanticExtractor(BaseExtractor):
    @property
    def name(self) -> str:
        return "pydantic"

    @property
    def priority(self) -> int:
        return 90

    def can_extract(self, text: str) -> bool:
        return "BaseSettings" in text or "Field" in text

    def extract(
        self,
        file_path: Path,
        file_id: str,
        tree: Tree | None,
        text: str,
        seen_vars: Set[str],
    ) -> Generator[Union[Node, Edge], None, None]:

        # 1. Field(env="VAR") pattern
        field_env_pattern = r'Field\s*\([^)]*env\s*=\s*["\']([^"\']+)["\']'
        regex = re.compile(field_env_pattern, re.DOTALL)

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
                    "source": "pydantic_field",
                    "file": str(file_path),
                    "line": line,
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=env_id,
                type=RelationshipType.READS,
                metadata={"pattern": "pydantic_field", "line": line},
            )

        # 2. BaseSettings class pattern
        class_pattern = re.compile(
            r'class\s+(\w+)\s*\([^)]*BaseSettings[^)]*\)\s*:\s*\n(.*?)(?=\nclass\s+\w+\s*[\(:]|\Z)',
            re.DOTALL
        )

        for class_match in class_pattern.finditer(text):
            class_name = class_match.group(1)
            class_body = class_match.group(2)
            class_start_line = text[:class_match.start()].count('\n') + 1

            # Extract env_prefix from Config class
            prefix = ""
            prefix_match = re.search(
                r'class\s+Config\s*:.*?env_prefix\s*=\s*["\']([^"\']*)["\']',
                class_body,
                re.DOTALL
            )
            if prefix_match:
                prefix = prefix_match.group(1)

            # Find all typed field definitions (field_name: type)
            field_pattern = re.compile(
                r'^([ \t]{4}(\w+)\s*:\s*\w+.*?)$',
                re.MULTILINE
            )

            for field_match in field_pattern.finditer(class_body):
                field_line_content = field_match.group(1)
                field_name = field_match.group(2)

                # Skip private fields, Config class, and model internals
                if field_name.startswith('_') or field_name in ('Config', 'model_config', 'model_fields'):
                    continue

                # Check explicit env= override
                explicit_env_match = re.search(
                    r'Field\s*\([^)]*\benv\s*=\s*["\']([^"\']+)["\']',
                    field_line_content
                )
                if explicit_env_match:
                    continue

                env_var_name = prefix + field_name.upper()
                
                if env_var_name in seen_vars:
                    continue

                field_line = class_start_line + class_body[:field_match.start()].count('\n')
                env_id = f"env:{env_var_name}"

                yield Node(
                    id=env_id,
                    name=env_var_name,
                    type=NodeType.ENV_VAR,
                    metadata={
                        "source": "pydantic_settings",
                        "file": str(file_path),
                        "line": field_line,
                        "settings_class": class_name,
                        "field_name": field_name,
                        "env_prefix": prefix,
                        "inferred": True,
                    },
                )

                yield Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={
                        "pattern": "pydantic_settings",
                        "env_prefix": prefix,
                        "line": field_line
                    },
                )
