"""
Standardized Terraform Parser.
"""

import re
from pathlib import Path
from typing import List, Union

from ...core.types import Node, Edge, NodeType, RelationshipType
from ..base import BaseParser


class TerraformParser(BaseParser):
    # Regex for output "name" { ... }
    OUTPUT_PATTERN = re.compile(r'output\s+"([^"]+)"\s+\{')
    # Regex for resource "type" "name" { ... }
    RESOURCE_PATTERN = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".tf"

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results: List[Union[Node, Edge]] = []
        text = content.decode("utf-8", errors="ignore")
        
        # 1. Parse Resources
        for match in self.RESOURCE_PATTERN.finditer(text):
            res_type, res_name = match.groups()
            # ID format: infra:type.name (or type:name depending on convention)
            # Using infra:type:name based on context
            node_id = f"infra:{res_type}:{res_name}"
            
            node = Node(
                id=node_id,
                name=res_name,
                type=NodeType.INFRA_RESOURCE,
                metadata={"terraform_type": res_type}
            )
            results.append(node)

        # 2. Parse Outputs
        for match in self.OUTPUT_PATTERN.finditer(text):
            out_name = match.groups()[0]
            node_id = f"infra:output:{out_name}"
            
            node = Node(
                id=node_id,
                name=out_name,
                type=NodeType.CONFIG_KEY # Terraform outputs act as config keys often
            )
            results.append(node)
            
            # Note: Parsing logic to connect Output -> Resource is complex in regex
            # We omit the edge creation inside the parser for regex based,
            # usually relying on the Stitcher or robust HCL parser.
            
        return results