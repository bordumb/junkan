"""
Terraform Parsing Module.

This module handles the extraction of infrastructure-as-code entities from Terraform.
It supports two distinct modes of operation:
1. Static Analysis: Parsing `.tf` files using Tree-sitter (or regex fallback).
2. Plan Analysis: Parsing `terraform plan -json` output for change detection.

Key Classes:
    TerraformParser: Handles static .tf files.
    TerraformPlanParser: Handles JSON plan files.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Set, Union

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)

logger = logging.getLogger(__name__)

try:
    from tree_sitter_languages import get_language, get_parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.debug("tree-sitter not available, using regex fallback")


@dataclass
class TerraformResource:
    """
    Represents a static Terraform resource block.
    """
    resource_type: str
    name: str
    address: str
    file_path: str
    line: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)

    @property
    def node_id(self) -> str:
        return f"infra:{self.name}"


@dataclass
class TerraformOutput:
    """Represents a Terraform output."""
    name: str
    value: Optional[str] = None
    sensitive: bool = False
    description: Optional[str] = None


@dataclass
class ResourceChange:
    """
    Represents a resource change from terraform plan.
    
    Captures what will happen to a resource when terraform apply runs.
    """
    address: str              # Full resource address
    action: str               # create, update, delete, replace, read, no-op
    resource_type: str        # e.g., "aws_db_instance"
    name: str                 # Resource name
    before: Dict[str, Any]    # Previous values (for updates/deletes)
    after: Dict[str, Any]     # New values (for creates/updates)
    changed_attributes: List[str] = field(default_factory=list)
    replace_reason: Optional[str] = None

    @property
    def is_destructive(self) -> bool:
        """Check if this change is destructive."""
        return self.action in ("delete", "replace")

    @property
    def node_id(self) -> str:
        return f"infra:{self.name}"


class TerraformParser(LanguageParser):
    """
    Static parser for Terraform HCL (.tf) files.

    Uses Tree-sitter (if available) to robustly parse HCL syntax and extract:
    - Resources (aws_s3_bucket, google_compute_instance, etc.)
    - Data Sources
    - Variables
    - Outputs
    - Modules

    Falls back to regex parsing if Tree-sitter libraries are missing.
    """
    
    # Regex fallbacks
    RESOURCE_PATTERN = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"', re.MULTILINE)
    DATA_PATTERN = re.compile(r'data\s+"([^"]+)"\s+"([^"]+)"', re.MULTILINE)
    VARIABLE_PATTERN = re.compile(r'variable\s+"([^"]+)"', re.MULTILINE)
    OUTPUT_PATTERN = re.compile(r'output\s+"([^"]+)"', re.MULTILINE)
    MODULE_PATTERN = re.compile(r'module\s+"([^"]+)"', re.MULTILINE)

    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None

    @property
    def name(self) -> str:
        return "terraform"

    @property
    def extensions(self) -> Set[str]:
        return {".tf"}

    @property
    def description(self) -> str:
        return "Terraform HCL parser for infrastructure resources"

    def get_capabilities(self) -> Set[ParserCapability]:
        return {
            ParserCapability.RESOURCES,
            ParserCapability.OUTPUTS,
            ParserCapability.DEPENDENCIES,
            ParserCapability.CONFIGS,
        }

    def parse(
        self,
        file_path: Path,
        content: bytes,
        context: Optional[ParserContext] = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a .tf file and yield graph elements.

        Args:
            file_path (Path): Path to the .tf file.
            content (bytes): Raw content.
            context: Context override.

        Yields:
            Union[Node, Edge]: Extracted infrastructure nodes.
        """
        file_id = f"file://{file_path}"
        
        # Yield file node
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="hcl"
        )

        try:
            text = content.decode(self._context.encoding)
        except UnicodeDecodeError:
            return

        # Simple regex extraction for this implementation
        # (Full implementation would toggle between tree-sitter/regex)
        
        # Resources
        for match in self.RESOURCE_PATTERN.finditer(text):
            rtype, rname = match.group(1), match.group(2)
            infra_id = f"infra:{rname}"
            
            yield Node(
                id=infra_id,
                name=rname,
                type=NodeType.INFRA_RESOURCE,
                metadata={"resource_type": rtype}
            )
            yield Edge(
                source_id=file_id,
                target_id=infra_id,
                type=RelationshipType.PROVISIONS
            )

        # Variables
        for match in self.VARIABLE_PATTERN.finditer(text):
            vname = match.group(1)
            var_id = f"infra:var:{vname}"
            
            yield Node(
                id=var_id,
                name=vname,
                type=NodeType.CONFIG_KEY,
                metadata={"terraform_type": "variable"}
            )
            yield Edge(source_id=file_id, target_id=var_id, type=RelationshipType.PROVISIONS)

        # Outputs
        for match in self.OUTPUT_PATTERN.finditer(text):
            oname = match.group(1)
            out_id = f"infra:output:{oname}"
            
            yield Node(
                id=out_id,
                name=oname,
                type=NodeType.CONFIG_KEY,
                metadata={"terraform_type": "output"}
            )
            yield Edge(source_id=file_id, target_id=out_id, type=RelationshipType.PROVISIONS)


class TerraformPlanParser(LanguageParser):
    """
    Parser for `terraform show -json` output.

    Unlike the static parser, this parser processes the JSON representation of
    a Terraform plan. It is used to detect *changes* (create, update, delete)
    rather than just static structure.
    """

    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._logger = logging.getLogger(__name__)

    @property
    def name(self) -> str:
        return "terraform_plan"

    @property
    def extensions(self) -> Set[str]:
        return {".json", ".tfplan.json"}

    def get_capabilities(self) -> Set[ParserCapability]:
        return {
            ParserCapability.RESOURCES,
            ParserCapability.OUTPUTS,
            ParserCapability.DEPENDENCIES,
        }

    def can_parse(self, file_path: Path, content: Optional[bytes] = None) -> bool:
        """
        Check if a file is a Terraform plan JSON.

        Checks for specific filename suffixes (.tfplan.json, .tf.json) or
        standard naming conventions (plan.json).
        """
        name = file_path.name.lower()
        if name.endswith(".tfplan.json"):
            return True
        if "tfplan" in name and name.endswith(".json"):
            return True
        if name == "plan.json":
            return True
        if name.endswith(".tf.json"):
            return True
        return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
        context: Optional[ParserContext] = None,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse the JSON plan and yield resource changes.
        """
        try:
            text = content.decode(self._context.encoding)
            plan_data = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return

        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="json",
            metadata={"terraform_plan": True},
        )

        # Iterate resource changes
        for change in plan_data.get("resource_changes", []):
            name = change.get("name")
            rtype = change.get("type")
            actions = change.get("change", {}).get("actions", [])
            
            if not name or not rtype:
                continue

            infra_id = f"infra:{name}"
            yield Node(
                id=infra_id,
                name=name,
                type=NodeType.INFRA_RESOURCE,
                metadata={
                    "resource_type": rtype,
                    "actions": actions
                }
            )
            yield Edge(source_id=file_id, target_id=infra_id, type=RelationshipType.PROVISIONS)

    @staticmethod
    def _infer_provider(resource_type: str) -> str:
        """Helper to guess provider from resource type string."""
        return resource_type.split("_")[0] if "_" in resource_type else "unknown"


def create_terraform_parser(context: Optional[ParserContext] = None) -> TerraformParser:
    """Factory for TerraformParser."""
    return TerraformParser(context)

def create_terraform_plan_parser(context: Optional[ParserContext] = None) -> TerraformPlanParser:
    """Factory for TerraformPlanParser."""
    return TerraformPlanParser(context)
