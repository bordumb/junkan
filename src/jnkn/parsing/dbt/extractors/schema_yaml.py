from typing import Generator, Union

try:
    import yaml
except ImportError:
    yaml = None

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class SchemaYamlExtractor:
    """Extract model and column definitions from schema.yml files."""

    name = "dbt_schema"
    priority = 80

    def can_extract(self, ctx: ExtractionContext) -> bool:
        if yaml is None:
            return False
        name = ctx.file_path.name.lower()
        return name.endswith(".yml") or name.endswith(".yaml")

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        try:
            data = yaml.safe_load(ctx.text)
        except yaml.YAMLError:
            return

        if not isinstance(data, dict):
            return

        # Extract models
        for model in data.get("models", []):
            model_name = model.get("name")
            if not model_name:
                continue

            model_id = f"data:model:{model_name}"

            # Extract columns
            columns = []

            for col in model.get("columns", []):
                col_name = col.get("name")
                columns.append(
                    {
                        "name": col_name,
                        "description": col.get("description"),
                        "data_type": col.get("data_type"),
                        "tests": col.get("tests", []),
                    }
                )

                # Create test relationships
                for test in col.get("tests", []):
                    test_name = test if isinstance(test, str) else list(test.keys())[0]
                    test_id = f"test:{model_name}:{col_name}:{test_name}"

                    yield Node(
                        id=test_id,
                        name=f"{test_name}({col_name})",
                        type=NodeType.JOB,
                        path=str(ctx.file_path),
                        metadata={
                            "test_type": test_name,
                            "column": col_name,
                            "model": model_name,
                        },
                    )

                    yield Edge(
                        source_id=test_id,
                        target_id=model_id,
                        type=RelationshipType.DEPENDS_ON,
                    )

            # Update model node with column info
            yield Node(
                id=model_id,
                name=model_name,
                type=NodeType.DATA_ASSET,
                path=str(ctx.file_path),
                metadata={
                    "description": model.get("description"),
                    "columns": columns,
                    "from_schema_yaml": True,
                },
            )

        # Extract sources
        for source in data.get("sources", []):
            source_name = source.get("name")

            for table in source.get("tables", []):
                table_name = table.get("name")
                source_id = f"data:source:{source_name}.{table_name}"

                yield Node(
                    id=source_id,
                    name=table_name,
                    type=NodeType.DATA_ASSET,
                    path=str(ctx.file_path),
                    metadata={
                        "resource_type": "source",
                        "source_name": source_name,
                        "description": table.get("description"),
                        "database": source.get("database"),
                        "schema": source.get("schema"),
                        "freshness": table.get("freshness"),
                    },
                )
