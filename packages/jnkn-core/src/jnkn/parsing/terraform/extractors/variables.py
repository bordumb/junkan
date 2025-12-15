import re
from dataclasses import dataclass
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


@dataclass
class TerraformVariable:
    name: str
    default: str | None
    description: str | None
    type_hint: str | None
    line: int


class VariableExtractor:
    """Extract variable blocks from Terraform files."""

    name = "terraform_variables"
    priority = 80

    # variable "name" { ... }
    VAR_PATTERN = re.compile(r'variable\s+"([^"]+)"\s*\{([^}]*)\}', re.DOTALL)
    DEFAULT_PATTERN = re.compile(r"default\s*=\s*(.+?)(?:\n|$)")
    DESC_PATTERN = re.compile(r'description\s*=\s*"([^"]*)"')
    TYPE_PATTERN = re.compile(r"type\s*=\s*(\w+)")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "variable" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.VAR_PATTERN.finditer(ctx.text):
            var_name = match.group(1)
            var_body = match.group(2)
            line = ctx.get_line_number(match.start())

            # Parse attributes
            default = None
            if dm := self.DEFAULT_PATTERN.search(var_body):
                default = dm.group(1).strip()

            description = None
            if dm := self.DESC_PATTERN.search(var_body):
                description = dm.group(1)

            type_hint = None
            if tm := self.TYPE_PATTERN.search(var_body):
                type_hint = tm.group(1)

            var_id = f"infra:var:{var_name}"

            # Use factory method for config/variables
            yield ctx.create_config_node(
                id=var_id,
                name=var_name,
                line=line,
                config_type="terraform_variable",
                extra_metadata={
                    "terraform_type": "variable",
                    "default": default,
                    "description": description,
                    "type_hint": type_hint,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=var_id,
                type=RelationshipType.CONTAINS,
            )
