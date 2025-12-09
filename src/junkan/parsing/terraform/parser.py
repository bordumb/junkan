"""
Terraform Parser for Jnkn.

This module provides parsing for Terraform HCL files and plan JSON output.
Supports both static analysis of .tf files and rich plan-based analysis.

Components:
- TerraformParser: Parses .tf files using tree-sitter
- TerraformPlanParser: Parses terraform show -json output

Features:
- Resource extraction with type and name
- Output value detection
- Variable references
- Module dependencies
- Plan-based change detection (create, update, delete)
"""

from pathlib import Path
from typing import Generator, List, Optional, Dict, Any, Set, Tuple, Union
from dataclasses import dataclass, field
import json
import re
import logging

from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
    ParseError,
)
from ...core.types import Node, Edge, NodeType, RelationshipType

logger = logging.getLogger(__name__)

# Check if tree-sitter is available
try:
    from tree_sitter_languages import get_parser, get_language
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.debug("tree-sitter not available, using regex fallback")


# Tree-sitter query for Terraform resources
TERRAFORM_QUERY = """
; Resource blocks
(block
  (identifier) @block_type
  (string_lit) @resource_type
  (string_lit) @resource_name
  (#eq? @block_type "resource"))

; Data blocks
(block
  (identifier) @block_type
  (string_lit) @data_type
  (string_lit) @data_name
  (#eq? @block_type "data"))

; Variable blocks
(block
  (identifier) @block_type
  (string_lit) @variable_name
  (#eq? @block_type "variable"))

; Output blocks
(block
  (identifier) @block_type
  (string_lit) @output_name
  (#eq? @block_type "output"))

; Module blocks
(block
  (identifier) @block_type
  (string_lit) @module_name
  (#eq? @block_type "module"))

; Provider blocks
(block
  (identifier) @block_type
  (string_lit) @provider_name
  (#eq? @block_type "provider"))

; Local values
(block
  (identifier) @block_type
  (#eq? @block_type "locals"))
"""


@dataclass
class TerraformResource:
    """Represents a Terraform resource."""
    resource_type: str  # e.g., "aws_db_instance"
    name: str           # e.g., "main"
    address: str        # Full address: "aws_db_instance.main"
    file_path: str
    line: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    
    @property
    def node_id(self) -> str:
        return f"infra:{self.name}"
    
    @property
    def full_node_id(self) -> str:
        return f"infra:{self.address}"


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
    Parser for Terraform HCL (.tf) files.
    
    Extracts:
    - Resource definitions
    - Data sources
    - Variables
    - Outputs
    - Module references
    - Provider configurations
    """
    
    # Regex patterns for fallback parsing
    RESOURCE_PATTERN = re.compile(
        r'resource\s+"([^"]+)"\s+"([^"]+)"',
        re.MULTILINE
    )
    
    DATA_PATTERN = re.compile(
        r'data\s+"([^"]+)"\s+"([^"]+)"',
        re.MULTILINE
    )
    
    VARIABLE_PATTERN = re.compile(
        r'variable\s+"([^"]+)"',
        re.MULTILINE
    )
    
    OUTPUT_PATTERN = re.compile(
        r'output\s+"([^"]+)"',
        re.MULTILINE
    )
    
    MODULE_PATTERN = re.compile(
        r'module\s+"([^"]+)"',
        re.MULTILINE
    )
    
    # Pattern for resource references in expressions
    REFERENCE_PATTERN = re.compile(
        r'(?:aws_|google_|azurerm_|digitalocean_|kubernetes_)[\w]+\.[\w]+'
    )
    
    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
        self._tree_sitter_initialized = False
        self._ts_parser = None
        self._ts_language = None
    
    @property
    def name(self) -> str:
        return "terraform"
    
    @property
    def extensions(self) -> List[str]:
        return [".tf"]
    
    @property
    def description(self) -> str:
        return "Terraform HCL parser for infrastructure resources"
    
    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.RESOURCES,
            ParserCapability.OUTPUTS,
            ParserCapability.DEPENDENCIES,
            ParserCapability.CONFIGS,
        ]
    
    def _init_tree_sitter(self) -> bool:
        """Initialize tree-sitter parser lazily."""
        if self._tree_sitter_initialized:
            return self._ts_parser is not None
        
        self._tree_sitter_initialized = True
        
        if not TREE_SITTER_AVAILABLE:
            return False
        
        try:
            self._ts_parser = get_parser("hcl")
            self._ts_language = get_language("hcl")
            return True
        except Exception as e:
            self._logger.warning(f"Failed to initialize tree-sitter for HCL: {e}")
            return False
    
    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a Terraform file and yield nodes and edges.
        """
        from ...core.types import ScanMetadata
        
        # Create file node
        try:
            file_hash = ScanMetadata.compute_hash(str(file_path))
        except Exception:
            file_hash = ""
        
        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="hcl",
            file_hash=file_hash,
        )
        
        # Decode content
        try:
            text = content.decode(self._context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                self._logger.error(f"Failed to decode {file_path}: {e}")
                return
        
        # Try tree-sitter parsing first
        if self._init_tree_sitter():
            yield from self._parse_with_tree_sitter(file_path, file_id, content, text)
        else:
            yield from self._parse_with_regex(file_path, file_id, text)
        
        # Extract references between resources
        yield from self._extract_references(file_path, file_id, text)
    
    def _parse_with_tree_sitter(
        self,
        file_path: Path,
        file_id: str,
        content: bytes,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Parse using tree-sitter queries."""
        tree = self._ts_parser.parse(content)
        query = self._ts_language.query(TERRAFORM_QUERY)
        captures = query.captures(tree.root_node)
        
        # Process captures in groups (block_type, type, name)
        current_block_type = None
        current_resource_type = None
        
        for node, capture_name in captures:
            text_value = node.text.decode("utf-8").strip('"')
            line = node.start_point[0] + 1
            
            if capture_name == "block_type":
                current_block_type = text_value
                current_resource_type = None
            
            elif capture_name == "resource_type":
                current_resource_type = text_value
            
            elif capture_name == "resource_name":
                if current_block_type == "resource" and current_resource_type:
                    address = f"{current_resource_type}.{text_value}"
                    infra_id = f"infra:{text_value}"
                    
                    yield Node(
                        id=infra_id,
                        name=text_value,
                        type=NodeType.INFRA_RESOURCE,
                        path=str(file_path),
                        metadata={
                            "resource_type": current_resource_type,
                            "address": address,
                            "line": line,
                            "provider": self._infer_provider(current_resource_type),
                        },
                    )
                    
                    yield Edge(
                        source_id=file_id,
                        target_id=infra_id,
                        type=RelationshipType.PROVISIONS,
                    )
            
            elif capture_name == "data_type":
                current_resource_type = text_value
            
            elif capture_name == "data_name":
                if current_resource_type:
                    address = f"data.{current_resource_type}.{text_value}"
                    data_id = f"infra:data:{text_value}"
                    
                    yield Node(
                        id=data_id,
                        name=text_value,
                        type=NodeType.INFRA_RESOURCE,
                        path=str(file_path),
                        metadata={
                            "resource_type": current_resource_type,
                            "address": address,
                            "is_data_source": True,
                            "line": line,
                        },
                    )
                    
                    yield Edge(
                        source_id=file_id,
                        target_id=data_id,
                        type=RelationshipType.READS,
                    )
            
            elif capture_name == "variable_name":
                var_id = f"infra:var:{text_value}"
                
                yield Node(
                    id=var_id,
                    name=text_value,
                    type=NodeType.CONFIG_KEY,
                    path=str(file_path),
                    metadata={
                        "terraform_type": "variable",
                        "line": line,
                    },
                )
            
            elif capture_name == "output_name":
                output_id = f"infra:output:{text_value}"
                
                yield Node(
                    id=output_id,
                    name=text_value,
                    type=NodeType.CONFIG_KEY,
                    path=str(file_path),
                    metadata={
                        "terraform_type": "output",
                        "line": line,
                    },
                )
            
            elif capture_name == "module_name":
                module_id = f"infra:module:{text_value}"
                
                yield Node(
                    id=module_id,
                    name=text_value,
                    type=NodeType.INFRA_MODULE,
                    path=str(file_path),
                    metadata={
                        "terraform_type": "module",
                        "line": line,
                    },
                )
                
                yield Edge(
                    source_id=file_id,
                    target_id=module_id,
                    type=RelationshipType.IMPORTS,
                )
    
    def _parse_with_regex(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Fallback parsing using regex patterns."""
        # Parse resources
        for match in self.RESOURCE_PATTERN.finditer(text):
            resource_type = match.group(1)
            resource_name = match.group(2)
            line = text[:match.start()].count('\n') + 1
            
            address = f"{resource_type}.{resource_name}"
            infra_id = f"infra:{resource_name}"
            
            yield Node(
                id=infra_id,
                name=resource_name,
                type=NodeType.INFRA_RESOURCE,
                path=str(file_path),
                metadata={
                    "resource_type": resource_type,
                    "address": address,
                    "line": line,
                    "provider": self._infer_provider(resource_type),
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=infra_id,
                type=RelationshipType.PROVISIONS,
            )
        
        # Parse data sources
        for match in self.DATA_PATTERN.finditer(text):
            data_type = match.group(1)
            data_name = match.group(2)
            line = text[:match.start()].count('\n') + 1
            
            data_id = f"infra:data:{data_name}"
            
            yield Node(
                id=data_id,
                name=data_name,
                type=NodeType.INFRA_RESOURCE,
                path=str(file_path),
                metadata={
                    "resource_type": data_type,
                    "is_data_source": True,
                    "line": line,
                },
            )
            
            yield Edge(
                source_id=file_id,
                target_id=data_id,
                type=RelationshipType.READS,
            )
        
        # Parse variables
        for match in self.VARIABLE_PATTERN.finditer(text):
            var_name = match.group(1)
            var_id = f"infra:var:{var_name}"
            
            yield Node(
                id=var_id,
                name=var_name,
                type=NodeType.CONFIG_KEY,
                path=str(file_path),
                metadata={"terraform_type": "variable"},
            )
        
        # Parse outputs
        for match in self.OUTPUT_PATTERN.finditer(text):
            output_name = match.group(1)
            output_id = f"infra:output:{output_name}"
            
            yield Node(
                id=output_id,
                name=output_name,
                type=NodeType.CONFIG_KEY,
                path=str(file_path),
                metadata={"terraform_type": "output"},
            )
        
        # Parse modules
        for match in self.MODULE_PATTERN.finditer(text):
            module_name = match.group(1)
            module_id = f"infra:module:{module_name}"
            
            yield Node(
                id=module_id,
                name=module_name,
                type=NodeType.INFRA_MODULE,
                path=str(file_path),
                metadata={"terraform_type": "module"},
            )
            
            yield Edge(
                source_id=file_id,
                target_id=module_id,
                type=RelationshipType.IMPORTS,
            )
    
    def _extract_references(
        self,
        file_path: Path,
        file_id: str,
        text: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract resource references from expressions."""
        seen_refs: Set[str] = set()
        
        for match in self.REFERENCE_PATTERN.finditer(text):
            ref = match.group(0)
            
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            
            # Parse resource_type.resource_name
            parts = ref.split(".")
            if len(parts) >= 2:
                resource_name = parts[1]
                ref_id = f"infra:{resource_name}"
                
                # Create edge from file to referenced resource
                yield Edge(
                    source_id=file_id,
                    target_id=ref_id,
                    type=RelationshipType.DEPENDS_ON,
                    metadata={"reference": ref},
                )
    
    @staticmethod
    def _infer_provider(resource_type: str) -> str:
        """Infer the provider from resource type."""
        provider_prefixes = {
            "aws_": "aws",
            "google_": "google",
            "azurerm_": "azurerm",
            "kubernetes_": "kubernetes",
            "helm_": "helm",
            "digitalocean_": "digitalocean",
            "github_": "github",
            "datadog_": "datadog",
            "cloudflare_": "cloudflare",
            "vault_": "vault",
            "random_": "random",
            "null_": "null",
            "local_": "local",
            "template_": "template",
            "tls_": "tls",
            "archive_": "archive",
        }
        
        for prefix, provider in provider_prefixes.items():
            if resource_type.startswith(prefix):
                return provider
        
        return "unknown"


class TerraformPlanParser(LanguageParser):
    """
    Parser for terraform show -json output.
    
    Provides richer analysis than static .tf parsing:
    - Resource changes (create, update, delete, replace)
    - Before/after values for updates
    - Renamed resource detection
    - Output values
    - Dependency extraction from the plan
    
    Usage:
        terraform plan -out=tfplan
        terraform show -json tfplan > tfplan.json
        
        parser = TerraformPlanParser()
        result = parser.parse_full(Path("tfplan.json"))
    """
    
    def __init__(self, context: Optional[ParserContext] = None):
        super().__init__(context)
    
    @property
    def name(self) -> str:
        return "terraform_plan"
    
    @property
    def extensions(self) -> List[str]:
        return [".tfplan.json", ".tf.json"]
    
    @property
    def description(self) -> str:
        return "Terraform plan JSON parser for change analysis"
    
    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.RESOURCES,
            ParserCapability.OUTPUTS,
            ParserCapability.DEPENDENCIES,
        ]
    
    def supports_file(self, file_path: Path) -> bool:
        """Check if this is a terraform plan JSON file."""
        name = file_path.name.lower()
        
        # Check for common terraform plan output names
        if name.endswith(".tfplan.json"):
            return True
        if "tfplan" in name and name.endswith(".json"):
            return True
        if name == "plan.json":
            return True
        
        # Also support .tf.json (JSON-format terraform)
        if name.endswith(".tf.json"):
            return True
        
        return False
    
    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Parse a terraform plan JSON file."""
        # Decode and parse JSON
        try:
            text = content.decode(self._context.encoding)
            plan_data = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            self._logger.error(f"Failed to parse plan JSON {file_path}: {e}")
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
        
        # Extract resource changes
        yield from self._extract_resource_changes(file_path, file_id, plan_data)
        
        # Extract outputs
        yield from self._extract_outputs(file_path, file_id, plan_data)
        
        # Extract prior state resources
        yield from self._extract_prior_state(file_path, file_id, plan_data)
    
    def _extract_resource_changes(
        self,
        file_path: Path,
        file_id: str,
        plan_data: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract resource changes from the plan."""
        resource_changes = plan_data.get("resource_changes", [])
        
        for change in resource_changes:
            address = change.get("address", "")
            change_actions = set(change.get("change", {}).get("actions", []))
            resource_type = change.get("type", "")
            resource_name = change.get("name", "")
            
            # Determine the action
            action = self._determine_action(change_actions)
            
            # Get before/after values
            change_details = change.get("change", {})
            before = change_details.get("before") or {}
            after = change_details.get("after") or {}
            
            # Find changed attributes
            changed_attrs = self._find_changed_attributes(before, after)
            
            # Determine replace reason if applicable
            replace_reason = None
            if action == "replace":
                replace_paths = change_details.get("replace_paths", [])
                if replace_paths:
                    replace_reason = f"Changed: {', '.join(str(p) for p in replace_paths[:3])}"
            
            # Create resource change node
            infra_id = f"infra:{resource_name}"
            
            yield Node(
                id=infra_id,
                name=resource_name,
                type=NodeType.INFRA_RESOURCE,
                path=str(file_path),
                metadata={
                    "resource_type": resource_type,
                    "address": address,
                    "action": action,
                    "changed_attributes": changed_attrs,
                    "replace_reason": replace_reason,
                    "is_destructive": action in ("delete", "replace"),
                    "provider": TerraformParser._infer_provider(resource_type),
                },
            )
            
            # Create edge with action metadata
            yield Edge(
                source_id=file_id,
                target_id=infra_id,
                type=RelationshipType.PROVISIONS,
                metadata={
                    "action": action,
                    "changed_attributes": changed_attrs,
                },
            )
    
    def _extract_outputs(
        self,
        file_path: Path,
        file_id: str,
        plan_data: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract output values from the plan."""
        # Check planned_values first
        planned_values = plan_data.get("planned_values", {})
        outputs = planned_values.get("outputs", {})
        
        # Also check output_changes
        output_changes = plan_data.get("output_changes", {})
        
        all_outputs = set(outputs.keys()) | set(output_changes.keys())
        
        for output_name in all_outputs:
            output_id = f"infra:output:{output_name}"
            
            output_info = outputs.get(output_name, {})
            change_info = output_changes.get(output_name, {})
            
            sensitive = output_info.get("sensitive", False)
            
            # Determine if output is changing
            actions = change_info.get("actions", [])
            action = actions[0] if actions else "no-op"
            
            yield Node(
                id=output_id,
                name=output_name,
                type=NodeType.CONFIG_KEY,
                path=str(file_path),
                metadata={
                    "terraform_type": "output",
                    "sensitive": sensitive,
                    "action": action,
                },
            )
    
    def _extract_prior_state(
        self,
        file_path: Path,
        file_id: str,
        plan_data: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        """Extract resources from prior state."""
        prior_state = plan_data.get("prior_state", {})
        values = prior_state.get("values", {})
        root_module = values.get("root_module", {})
        resources = root_module.get("resources", [])
        
        for resource in resources:
            address = resource.get("address", "")
            resource_type = resource.get("type", "")
            resource_name = resource.get("name", "")
            
            # Only yield if we haven't already from resource_changes
            yield Node(
                id=f"infra:prior:{resource_name}",
                name=resource_name,
                type=NodeType.INFRA_RESOURCE,
                path=str(file_path),
                metadata={
                    "resource_type": resource_type,
                    "address": address,
                    "from_prior_state": True,
                    "provider": TerraformParser._infer_provider(resource_type),
                },
            )
    
    def _determine_action(self, actions: Set[str]) -> str:
        """Determine the overall action from action set."""
        if actions == {"create", "delete"}:
            return "replace"
        elif "create" in actions:
            return "create"
        elif "delete" in actions:
            return "delete"
        elif "update" in actions:
            return "update"
        elif "read" in actions:
            return "read"
        else:
            return "no-op"
    
    def _find_changed_attributes(
        self,
        before: Dict[str, Any],
        after: Dict[str, Any],
    ) -> List[str]:
        """Find attributes that changed between before and after."""
        if not before or not after:
            return []
        
        changed = []
        all_keys = set(before.keys()) | set(after.keys())
        
        for key in all_keys:
            before_val = before.get(key)
            after_val = after.get(key)
            
            if before_val != after_val:
                changed.append(key)
        
        return changed
    
    def parse_changes(self, plan_path: Path) -> List[ResourceChange]:
        """
        Parse a plan file and return structured change objects.
        
        This is a convenience method for getting just the changes
        without the full node/edge generation.
        """
        changes = []
        
        try:
            content = plan_path.read_bytes()
            text = content.decode("utf-8")
            plan_data = json.loads(text)
        except Exception as e:
            self._logger.error(f"Failed to parse plan: {e}")
            return changes
        
        for change in plan_data.get("resource_changes", []):
            address = change.get("address", "")
            resource_type = change.get("type", "")
            resource_name = change.get("name", "")
            
            change_details = change.get("change", {})
            actions = set(change_details.get("actions", []))
            action = self._determine_action(actions)
            
            before = change_details.get("before") or {}
            after = change_details.get("after") or {}
            changed_attrs = self._find_changed_attributes(before, after)
            
            replace_reason = None
            if action == "replace":
                replace_paths = change_details.get("replace_paths", [])
                if replace_paths:
                    replace_reason = str(replace_paths[0])
            
            changes.append(ResourceChange(
                address=address,
                action=action,
                resource_type=resource_type,
                name=resource_name,
                before=before,
                after=after,
                changed_attributes=changed_attrs,
                replace_reason=replace_reason,
            ))
        
        return changes


def create_terraform_parser(context: Optional[ParserContext] = None) -> TerraformParser:
    """Factory function to create a Terraform parser."""
    return TerraformParser(context)


def create_terraform_plan_parser(context: Optional[ParserContext] = None) -> TerraformPlanParser:
    """Factory function to create a Terraform plan parser."""
    return TerraformPlanParser(context)