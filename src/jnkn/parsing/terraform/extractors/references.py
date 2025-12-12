import re
from typing import Generator, Optional, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class ReferenceExtractor:
    """Extract resource references from HCL expressions."""

    name = "terraform_references"
    priority = 40  # Runs last, after all resources are known

    # Patterns for Terraform references
    RESOURCE_REF = re.compile(r"\b(aws_\w+|google_\w+|azurerm_\w+)\.(\w+)\.(\w+)")
    VAR_REF = re.compile(r"\bvar\.(\w+)")
    LOCAL_REF = re.compile(r"\blocal\.(\w+)")
    DATA_REF = re.compile(r"\bdata\.(\w+)\.(\w+)\.(\w+)")
    MODULE_REF = re.compile(r"\bmodule\.(\w+)\.(\w+)")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return True  # Always run

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        # Only create edges, nodes should already exist from other extractors

        # Resource references
        for match in self.RESOURCE_REF.finditer(ctx.text):
            res_type, res_name, attr = match.groups()
            source_id = self._find_containing_block(ctx.text, match.start())
            target_id = f"infra:{res_type}:{res_name}"

            if source_id and source_id != target_id:
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=RelationshipType.DEPENDS_ON,
                    metadata={"attribute": attr},
                )

        # Variable references
        for match in self.VAR_REF.finditer(ctx.text):
            var_name = match.group(1)
            source_id = self._find_containing_block(ctx.text, match.start())
            target_id = f"infra:var:{var_name}"

            if source_id:
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=RelationshipType.READS,
                )

        # Local references
        for match in self.LOCAL_REF.finditer(ctx.text):
            local_name = match.group(1)
            source_id = self._find_containing_block(ctx.text, match.start())
            target_id = f"infra:local:{local_name}"

            if source_id:
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=RelationshipType.READS,
                )

    def _find_containing_block(self, text: str, pos: int) -> Optional[str]:
        """
        Locate the resource or block ID that contains the given position.
        Uses a heuristic searching backwards for 'resource' or 'module' declarations.
        """
        # Look backwards from 'pos' for the nearest block definition
        prefix = text[:pos]

        # Simple heuristic: find last occurrence of 'resource' or 'module' before open brace
        # Note: This is an approximation. A full HCL parser state machine is ideal.

        # Regex to find block headers: resource "type" "name" {
        block_pattern = re.compile(r'(resource|data|module)\s+"([^"]+)"\s+"?([^"]*)"?\s*\{')

        matches = list(block_pattern.finditer(prefix))
        if not matches:
            return None

        # Get the last match found before the reference
        last_match = matches[-1]

        # Basic scope check: ensure the block hasn't closed yet
        # Count braces between match end and ref pos
        between_text = prefix[last_match.end() :]
        open_braces = between_text.count("{")
        close_braces = between_text.count("}")

        # If balanced or closed more than opened, we are likely outside
        # Starting with 1 open brace from the match itself
        if 1 + open_braces - close_braces <= 0:
            return None

        block_type, type_arg, name_arg = last_match.groups()

        if block_type == "resource":
            return f"infra:{type_arg}:{name_arg}"
        elif block_type == "data":
            return f"infra:data.{type_arg}:{name_arg}"
        elif block_type == "module":
            return f"infra:module:{type_arg}"  # type_arg captures module name here

        return None
