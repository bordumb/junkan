"""Terraform Variable Extractor."""

import re
from typing import Generator, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class VariableExtractor:
    """Extract Terraform variable blocks."""

    name = "terraform_variables"
    priority = 85

    VARIABLE_PATTERN = re.compile(r'variable\s+"([^"]+)"\s*\{')

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return "variable" in ctx.text

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        for match in self.VARIABLE_PATTERN.finditer(ctx.text):
            var_name = match.group(1)
            line = ctx.get_line_number(match.start())

            # Use source_repo prefix for multi-repo support
            var_id = f"{ctx.infra_prefix}:var:{var_name}"

            yield ctx.create_config_node(
                id=var_id,
                name=var_name,
                line=line,
                config_type="terraform_variable",
                extra_metadata={"terraform_type": "variable"},
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=var_id,
                type=RelationshipType.PROVISIONS,
            )
