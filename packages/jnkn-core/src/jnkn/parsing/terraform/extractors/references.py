"""
Terraform Reference Extractor.

Identifies dependencies between artifacts by parsing HCL expressions
within resources, outputs, and modules.
"""

import re
from typing import Generator, Optional, Union

from ....core.types import Edge, Node, RelationshipType
from ...base import ExtractionContext


class ReferenceExtractor:
    """
    Extracts edges by identifying references in Terraform expressions.

    This extractor runs after node creation to link artifacts. It parses
    interpolations like 'aws_instance.web.id' or 'var.region' to establish
    DEPENDS_ON and READS relationships.
    """

    name = "terraform_references"
    priority = 40  # Runs last, after all resources are known

    # Patterns for Terraform references
    # Matches: type.name.attr (e.g. aws_instance.web.public_ip)
    RESOURCE_REF = re.compile(r"\b(aws_\w+|google_\w+|azurerm_\w+)\.(\w+)\.(\w+)")

    # Matches: var.name
    VAR_REF = re.compile(r"\bvar\.(\w+)")

    # Matches: local.name
    LOCAL_REF = re.compile(r"\blocal\.(\w+)")

    # Matches: data.type.name.attr
    DATA_REF = re.compile(r"\bdata\.(\w+)\.(\w+)\.(\w+)")

    # Matches: module.name.output
    MODULE_REF = re.compile(r"\bmodule\.(\w+)\.(\w+)")

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return True  # Always run to find connections

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        """
        Scan text for references and generate edges linking the containing block
        to the referenced artifact.
        """
        # 1. Resource References (Implicit Dependencies)
        for match in self.RESOURCE_REF.finditer(ctx.text):
            res_type, res_name, attr = match.groups()

            # Find what block contains this reference (Source)
            source_id = self._find_containing_block(ctx.text, match.start())

            # Construct the ID of the referenced resource (Target)
            target_id = f"infra:{res_type}.{res_name}"

            if source_id and source_id != target_id:
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=RelationshipType.DEPENDS_ON,
                    metadata={"attribute": attr},
                )

        # 2. Variable References (Input Reading)
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

        # 3. Local Value References
        for match in self.LOCAL_REF.finditer(ctx.text):
            local_name = match.group(1)
            source_id = self._find_containing_block(ctx.text, match.start())
            target_id = f"infra:local.{local_name}"

            if source_id:
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=RelationshipType.READS,
                )

        # 4. Module Output References
        for match in self.MODULE_REF.finditer(ctx.text):
            mod_name, output_name = match.groups()
            source_id = self._find_containing_block(ctx.text, match.start())
            target_id = f"infra:module:{mod_name}"

            if source_id:
                yield Edge(
                    source_id=source_id,
                    target_id=target_id,
                    type=RelationshipType.DEPENDS_ON,
                    metadata={"output": output_name},
                )

    def _find_containing_block(self, text: str, pos: int) -> Optional[str]:
        """
        Locate the ID of the block (resource, output, etc.) that contains the given position.

        Uses a heuristic search backwards from the reference position to find the
        nearest block declaration header.
        """
        prefix = text[:pos]

        # Regex to find block headers. Supports 1 or 2 arguments.
        # Captures:
        # 1. Block Type (resource, data, module, output)
        # 2. First Arg (type or name)
        # 3. Second Arg (optional name)
        # Examples:
        #   resource "aws_s3_bucket" "b" -> ('resource', 'aws_s3_bucket', 'b')
        #   output "url"                 -> ('output', 'url', None)
        block_pattern = re.compile(
            r'(resource|data|module|output)\s+"([^"]+)"(?:\s+"([^"]+)")?\s*\{'
        )

        matches = list(block_pattern.finditer(prefix))
        if not matches:
            return None

        # Get the last match found before the reference position
        last_match = matches[-1]

        # Scope Check: Ensure the block hasn't closed yet.
        # We count braces between the block start and the reference position.
        between_text = prefix[last_match.end() :]
        open_braces = between_text.count("{")
        close_braces = between_text.count("}")

        # Net open braces. Note: The match itself consumes the opening `{`
        # but regex might vary. Assuming the regex ends with `{`, the block is open.
        # If we see more closes than opens subsequently, we have exited the block.
        if open_braces < close_braces:
            return None

        block_type, arg1, arg2 = last_match.groups()

        if block_type == "resource":
            return f"infra:{arg1}.{arg2}"
        elif block_type == "data":
            return f"infra:data.{arg1}.{arg2}"
        elif block_type == "module":
            return f"infra:module:{arg1}"
        elif block_type == "output":
            return f"infra:output:{arg1}"

        return None
