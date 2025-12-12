"""
Standardized Terraform Parser.

Provides parsing for:
- Static .tf files (HCL)
- Terraform Plan JSON (tfplan.json)
"""

import json
from pathlib import Path
from typing import Generator, List, Union

from ...core.types import Edge, Node, NodeType
from ..base import (
    ExtractionContext,
    ExtractorRegistry,
    LanguageParser,
    ParserContext,
)
from .extractors.data_sources import DataSourceExtractor
from .extractors.locals import LocalsExtractor
from .extractors.modules import ModuleExtractor
from .extractors.outputs import OutputExtractor
from .extractors.references import ReferenceExtractor
from .extractors.resources import ResourceExtractor
from .extractors.variables import VariableExtractor


class TerraformParser(LanguageParser):
    """
    Static analysis parser for Terraform (.tf) files.
    Uses the unified Extractor Architecture.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        """Register all Terraform extractors."""
        self._extractors.register(ResourceExtractor())
        self._extractors.register(OutputExtractor())
        self._extractors.register(VariableExtractor())
        self._extractors.register(ModuleExtractor())
        self._extractors.register(DataSourceExtractor())
        self._extractors.register(LocalsExtractor())
        self._extractors.register(ReferenceExtractor())

    @property
    def name(self) -> str:
        return "terraform"

    @property
    def extensions(self) -> List[str]:
        return [".tf"]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        return file_path.suffix == ".tf"

    def parse(self, file_path: Path, content: bytes) -> Generator[Union[Node, Edge], None, None]:
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            return

        file_id = f"file://{file_path}"

        # 1. File Node
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            metadata={"language": "hcl"},
        )

        # 2. Run Extractors
        ctx = ExtractionContext(file_path=file_path, file_id=file_id, text=text, seen_ids=set())

        yield from self._extractors.extract_all(ctx)


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

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        # Heuristic: Check if filename looks like a plan
        if file_path.suffix == ".json" and "plan" in file_path.name.lower():
            return True

        # Check content if provided
        if content:
            try:
                # Lightweight check for plan structure
                start = content[:200].decode("utf-8", errors="ignore")
                return "resource_changes" in start or "terraform_version" in start
            except Exception:
                pass
        return False

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

            node_id = f"infra:{res_type}.{res_name}"

            node = Node(
                id=node_id,
                name=res_name,
                type=NodeType.INFRA_RESOURCE,
                metadata={
                    "terraform_address": address,
                    "change_actions": change.get("change", {}).get("actions", []),
                },
            )
            results.append(node)

        return results


def create_terraform_parser(context: ParserContext | None = None) -> TerraformParser:
    return TerraformParser(context)


def create_terraform_plan_parser(context: ParserContext | None = None) -> TerraformPlanParser:
    return TerraformPlanParser(context)
