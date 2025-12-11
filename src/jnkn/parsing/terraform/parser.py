"""
Standardized Terraform Parser.

Provides parsing for:
- Static .tf files (HCL)
- Terraform Plan JSON (tfplan.json)
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import LanguageParser, ParserContext


# =============================================================================
# Data Models (Required by __init__.py)
# =============================================================================

@dataclass
class TerraformResource:
    """Represents a Terraform resource block."""
    type: str
    name: str
    provider: str
    line: int

@dataclass
class TerraformOutput:
    """Represents a Terraform output block."""
    name: str
    description: Optional[str] = None
    line: int = 0

@dataclass
class ResourceChange:
    """Represents a change in a Terraform plan."""
    address: str
    type: str
    name: str
    change_type: str  # create, update, delete
    actions: List[str]


# =============================================================================
# Static Parser (for .tf files)
# =============================================================================

class TerraformParser(LanguageParser):
    """
    Static analysis parser for Terraform (.tf) files.
    """
    
    # Regex for output "name" { ... }
    OUTPUT_PATTERN = re.compile(r'output\s+"([^"]+)"\s+\{')
    # Regex for resource "type" "name" { ... }
    RESOURCE_PATTERN = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')

    @property
    def name(self) -> str:
        return "terraform"

    @property
    def extensions(self) -> List[str]:
        return [".tf"]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".tf"

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results: List[Union[Node, Edge]] = []
        
        try:
            text = content.decode("utf-8", errors="ignore")
        except Exception:
            return []
        
        file_id = f"file://{file_path}"
        
        # 1. File Node
        results.append(Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            metadata={"language": "hcl"}
        ))

        # 2. Parse Resources
        for match in self.RESOURCE_PATTERN.finditer(text):
            res_type, res_name = match.groups()
            node_id = f"infra:{res_type}:{res_name}"
            
            node = Node(
                id=node_id,
                name=res_name,
                type=NodeType.INFRA_RESOURCE,
                metadata={"terraform_type": res_type}
            )
            results.append(node)
            
            # Link file -> resource
            results.append(Edge(
                source_id=file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS
            ))

        # 3. Parse Outputs
        for match in self.OUTPUT_PATTERN.finditer(text):
            out_name = match.groups()[0]
            # Convention: infra:output:name
            node_id = f"infra:output:{out_name}"
            
            node = Node(
                id=node_id,
                name=out_name,
                type=NodeType.CONFIG_KEY
            )
            results.append(node)
            
            # Link file -> output
            results.append(Edge(
                source_id=file_id,
                target_id=node_id,
                type=RelationshipType.PROVISIONS
            ))
            
        return results


# =============================================================================
# Plan Parser (for tfplan.json)
# =============================================================================

class TerraformPlanParser(LanguageParser):
    """
    Parser for Terraform JSON plan output.
    """

    @property
    def name(self) -> str:
        return "terraform_plan"

    @property
    def extensions(self) -> List[str]:
        return [".json"]

    def can_parse(self, file_path: Path) -> bool:
        # Heuristic: Check if filename looks like a plan or content has specific keys
        return file_path.suffix == ".json" and "plan" in file_path.name.lower()

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results = []
        try:
            plan = json.loads(content)
        except json.JSONDecodeError:
            return []

        if "resource_changes" not in plan:
            return []

        for change in plan["resource_changes"]:
            res_type = change.get("type")
            res_name = change.get("name")
            address = change.get("address")
            
            if not res_type or not res_name:
                continue

            node_id = f"infra:{res_type}:{res_name}"
            
            node = Node(
                id=node_id,
                name=res_name,
                type=NodeType.INFRA_RESOURCE,
                metadata={
                    "terraform_address": address,
                    "change_actions": change.get("change", {}).get("actions", [])
                }
            )
            results.append(node)

        return results


# =============================================================================
# Factory Functions (Required by __init__.py)
# =============================================================================

def create_terraform_parser(context: Optional[ParserContext] = None) -> TerraformParser:
    """Factory for TerraformParser."""
    return TerraformParser(context)

def create_terraform_plan_parser(context: Optional[ParserContext] = None) -> TerraformPlanParser:
    """Factory for TerraformPlanParser."""
    return TerraformPlanParser(context)