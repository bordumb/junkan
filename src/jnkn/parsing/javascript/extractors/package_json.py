import json
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class PackageJsonExtractor:
    """Extract dependencies from package.json."""

    name = "package_json"
    priority = 40

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return ctx.file_path.name == "package.json"

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        try:
            pkg = json.loads(ctx.text)
        except json.JSONDecodeError:
            return

        pkg_name = pkg.get("name", ctx.file_path.parent.name)

        # Dependencies
        for dep_type in ("dependencies", "devDependencies", "peerDependencies"):
            for dep_name, version in pkg.get(dep_type, {}).items():
                dep_id = f"npm:{dep_name}"

                yield Node(
                    id=dep_id,
                    name=dep_name,
                    type=NodeType.CODE_ENTITY,
                    metadata={
                        "package_type": "npm",
                        "version": version,
                        "dependency_type": dep_type,
                        "virtual": True,
                    },
                )

                yield Edge(
                    source_id=ctx.file_id,
                    target_id=dep_id,
                    type=RelationshipType.DEPENDS_ON,
                    metadata={"version": version},
                )

        # Scripts (potential entry points)
        for script_name, script_cmd in pkg.get("scripts", {}).items():
            script_id = f"script:{pkg_name}:{script_name}"
            yield Node(
                id=script_id,
                name=script_name,
                type=NodeType.JOB,
                path=str(ctx.file_path),
                metadata={
                    "command": script_cmd,
                    "package": pkg_name,
                },
            )
            yield Edge(source_id=ctx.file_id, target_id=script_id, type=RelationshipType.CONTAINS)
