"""
dbt Manifest Parser for jnkn.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Generator, List, Union

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)

logger = logging.getLogger(__name__)

# --- Data Models ---


@dataclass
class DbtColumn:
    """Represents a column in a dbt model."""

    name: str
    description: str | None = None
    data_type: str | None = None
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DbtNode:
    """Represents a dbt node."""

    unique_id: str
    name: str
    resource_type: str
    schema_name: str
    database: str | None
    package_name: str
    original_file_path: str | None = None
    columns: List[DbtColumn] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)
    raw_sql: str | None = None
    description: str | None = None
    tags: List[str] = field(default_factory=list)
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DbtExposure:
    """Represents a dbt exposure."""

    unique_id: str
    name: str
    type: str
    owner: str | None = None
    description: str | None = None
    depends_on: List[str] = field(default_factory=list)
    url: str | None = None


# --- Parser ---


class DbtManifestParser(LanguageParser):
    """
    Parser for dbt manifest.json files.
    """

    NODE_TYPES = {"model", "source", "seed", "snapshot", "analysis"}

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)

    @property
    def name(self) -> str:
        return "dbt_manifest"

    @property
    def extensions(self) -> List[str]:
        return [".json"]

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.DEPENDENCIES,
            ParserCapability.OUTPUTS,
        ]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        """Check if this is a dbt manifest file."""
        name = file_path.name.lower()

        # Standard manifest location
        if name == "manifest.json":
            if file_path.parent.name == "target":
                return True
            return True

        if name in ("dbt_manifest.json", "manifest.dbt.json"):
            return True

        # Optional content check if name isn't definitive but ends in json
        if content and file_path.suffix == ".json":
            try:
                # Quick check first few bytes
                start = content[:500].decode("utf-8", errors="ignore")
                if "dbt_schema_version" in start:
                    return True
            except Exception:
                pass

        return False

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        try:
            text = content.decode(self.context.encoding)
            manifest = json.loads(text)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            self._logger.error(f"Failed to parse manifest {file_path}: {e}")
            return

        if not self._is_dbt_manifest(manifest):
            return

        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="json",
            metadata={
                "dbt_manifest": True,
                "dbt_schema_version": manifest.get("metadata", {}).get("dbt_schema_version"),
            },
        )

        yield from self._extract_nodes(file_path, file_id, manifest)
        yield from self._extract_sources(file_path, file_id, manifest)
        yield from self._extract_exposures(file_path, file_id, manifest)
        yield from self._extract_tests(file_path, file_id, manifest)

    def _is_dbt_manifest(self, data: Dict[str, Any]) -> bool:
        metadata = data.get("metadata", {})
        if "dbt_schema_version" in metadata:
            return True
        if "nodes" in data and "sources" in data:
            return True
        return False

    def _extract_nodes(
        self,
        file_path: Path,
        file_id: str,
        manifest: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        nodes = manifest.get("nodes", {})

        for unique_id, node_data in nodes.items():
            resource_type = node_data.get("resource_type", "")

            if resource_type not in self.NODE_TYPES:
                continue

            node_name = node_data.get("name", "")
            schema_name = node_data.get("schema", "")
            database = node_data.get("database")
            package_name = node_data.get("package_name", "")

            if resource_type == "model":
                data_id = f"data:model:{schema_name}.{node_name}"
            elif resource_type == "seed":
                data_id = f"data:seed:{schema_name}.{node_name}"
            elif resource_type == "snapshot":
                data_id = f"data:snapshot:{schema_name}.{node_name}"
            else:
                data_id = f"data:{resource_type}:{node_name}"

            columns = self._extract_columns(node_data.get("columns", {}))

            yield Node(
                id=data_id,
                name=node_name,
                type=NodeType.DATA_ASSET,
                path=node_data.get("original_file_path"),
                metadata={
                    "dbt_unique_id": unique_id,
                    "resource_type": resource_type,
                    "schema": schema_name,
                    "database": database,
                    "package": package_name,
                    "description": node_data.get("description"),
                    "tags": node_data.get("tags", []),
                    "columns": [c.name for c in columns],
                    "materialized": node_data.get("config", {}).get("materialized"),
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=data_id,
                type=RelationshipType.CONTAINS,
            )

            depends_on = node_data.get("depends_on", {}).get("nodes", [])
            for dep_id in depends_on:
                dep_node_id = self._convert_dbt_id_to_node_id(dep_id, manifest)
                if dep_node_id:
                    if dep_id.startswith("source."):
                        rel_type = RelationshipType.READS
                    else:
                        rel_type = RelationshipType.DEPENDS_ON

                    yield Edge(
                        source_id=data_id,
                        target_id=dep_node_id,
                        type=rel_type,
                        metadata={"dbt_dependency": True},
                    )

    def _extract_sources(
        self,
        file_path: Path,
        file_id: str,
        manifest: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        sources = manifest.get("sources", {})

        for unique_id, source_data in sources.items():
            source_name = source_data.get("name", "")
            schema_name = source_data.get("schema", "")
            database = source_data.get("database")
            source_definition = source_data.get("source_name", "")

            data_id = f"data:source:{source_definition}.{source_name}"
            columns = self._extract_columns(source_data.get("columns", {}))

            yield Node(
                id=data_id,
                name=source_name,
                type=NodeType.DATA_ASSET,
                metadata={
                    "dbt_unique_id": unique_id,
                    "resource_type": "source",
                    "schema": schema_name,
                    "database": database,
                    "source_definition": source_definition,
                    "description": source_data.get("description"),
                    "columns": [c.name for c in columns],
                },
            )

            yield Edge(
                source_id=file_id,
                target_id=data_id,
                type=RelationshipType.CONTAINS,
            )

    def _extract_exposures(
        self,
        file_path: Path,
        file_id: str,
        manifest: Dict[str, Any],
    ) -> Generator[Union[Node, Edge], None, None]:
        exposures = manifest.get("exposures", {})

        for unique_id, exposure_data in exposures.items():
            exposure_name = exposure_data.get("name", "")
            exposure_type = exposure_data.get("type", "")

            data_id = f"data:exposure:{exposure_name}"

            yield Node(
                id=data_id,
                name=exposure_name,
                type=NodeType.DATA_ASSET,
                metadata={
                    "dbt_unique_id": unique_id,
                    "resource_type": "exposure",
                    "exposure_type": exposure_type,
                    "description": exposure_data.get("description"),
                    "owner": exposure_data.get("owner", {}).get("name"),
                    "url": exposure_data.get("url"),
                },
            )

            depends_on = exposure_data.get("depends_on", {}).get("nodes", [])
            for dep_id in depends_on:
                dep_node_id = self._convert_dbt_id_to_node_id(dep_id, manifest)
                if dep_node_id:
                    yield Edge(
                        source_id=data_id,
                        target_id=dep_node_id,
                        type=RelationshipType.CONSUMES,
                    )

    def _extract_tests(self, file_path, file_id, manifest):
        return
        yield

    def _extract_columns(self, columns_data: Dict[str, Any]) -> List[DbtColumn]:
        columns = []
        for col_name, col_data in columns_data.items():
            columns.append(
                DbtColumn(
                    name=col_name,
                    description=col_data.get("description"),
                    data_type=col_data.get("data_type"),
                    tags=col_data.get("tags", []),
                    meta=col_data.get("meta", {}),
                )
            )
        return columns

    def _convert_dbt_id_to_node_id(
        self,
        dbt_id: str,
        manifest: Dict[str, Any],
    ) -> str | None:
        parts = dbt_id.split(".")
        if len(parts) < 3:
            return None

        resource_type = parts[0]

        if resource_type == "model":
            node_data = manifest.get("nodes", {}).get(dbt_id, {})
            schema_name = node_data.get("schema", "public")
            name = parts[-1]
            return f"data:model:{schema_name}.{name}"

        elif resource_type == "source":
            if len(parts) >= 4:
                source_name = parts[2]
                table_name = parts[3]
                return f"data:source:{source_name}.{table_name}"
            return None

        elif resource_type == "seed":
            node_data = manifest.get("nodes", {}).get(dbt_id, {})
            schema_name = node_data.get("schema", "public")
            name = parts[-1]
            return f"data:seed:{schema_name}.{name}"

        elif resource_type == "snapshot":
            node_data = manifest.get("nodes", {}).get(dbt_id, {})
            schema_name = node_data.get("schema", "public")
            name = parts[-1]
            return f"data:snapshot:{schema_name}.{name}"

        return None


def create_dbt_manifest_parser(context: ParserContext | None = None) -> DbtManifestParser:
    return DbtManifestParser(context)
