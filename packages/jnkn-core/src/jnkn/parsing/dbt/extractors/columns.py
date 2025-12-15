import logging
import re
from typing import Generator, Union

try:
    import sqlglot
    from sqlglot import exp

    SQLGLOT_AVAILABLE = True
except ImportError:
    SQLGLOT_AVAILABLE = False
    sqlglot = None  # Explicitly set to None for test mocking support
    exp = None  # Explicitly set to None for test mocking support

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import BaseExtractor, ExtractionContext

logger = logging.getLogger(__name__)


class DbtColumnExtractor(BaseExtractor):
    """
    Extracts column-level lineage from dbt SQL models.

    Sanitizes Jinja templates to produce valid SQL for parsing, then
    extracts referenced columns to build fine-grained dependencies.
    """

    name = "dbt_columns"
    priority = 80

    def can_extract(self, ctx: ExtractionContext) -> bool:
        return ctx.file_path.suffix == ".sql" and SQLGLOT_AVAILABLE

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        # 1. Sanitize Jinja to make it parsable SQL
        clean_sql = self._sanitize_jinja(ctx.text)

        try:
            parsed = sqlglot.parse_one(clean_sql)
        except Exception as e:
            logger.debug(f"Failed to parse dbt SQL in {ctx.file_path}: {e}")
            return

        # 2. Extract Column References
        model_name = ctx.file_path.stem
        model_node_id = f"data:model:{model_name}"

        # Check if exp is not None before using it (runtime safety)
        if exp and isinstance(parsed, exp.Select):
            for expression in parsed.expressions:
                if isinstance(expression, exp.Alias):
                    col_name = expression.alias
                elif isinstance(expression, exp.Column):
                    col_name = expression.name
                else:
                    continue

                col_id = f"column:{model_name}/{col_name}"

                yield Node(
                    id=col_id,
                    name=col_name,
                    type=NodeType.DATA_ASSET,
                    metadata={"is_column": True, "model": model_name, "file": str(ctx.file_path)},
                )

                yield Edge(
                    source_id=model_node_id, target_id=col_id, type=RelationshipType.CONTAINS
                )

    def _sanitize_jinja(self, text: str) -> str:
        # Remove config blocks
        text = re.sub(r"\{\{\s*config\s*\([^)]+\)\s*\}\}", "", text)

        # Replace ref('model') -> model
        text = re.sub(r"\{\{\s*ref\s*\(\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}", r"\1", text)

        # Replace source('s', 't') -> s.t
        text = re.sub(
            r"\{\{\s*source\s*\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*\}\}",
            r"\1.\2",
            text,
        )

        # Nuke remaining jinja variables
        text = re.sub(r"\{\{.*?\}\}", "1", text)
        text = re.sub(r"\{%.*?%\}", "", text, flags=re.DOTALL)

        return text
