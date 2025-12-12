import re
from typing import Generator, Union

from ....core.types import Edge, Node, NodeType, RelationshipType
from ...base import ExtractionContext


class SparkConfigExtractor:
    """Extract Spark configuration reads."""

    name = "spark_config"
    priority = 80

    # spark.conf.get("key") or spark.conf.get("key", "default")
    CONF_GET = re.compile(r'spark\.conf\.get\s*\(\s*["\']([^"\']+)["\']')
    # spark.conf.set("key", value)
    CONF_SET = re.compile(r'spark\.conf\.set\s*\(\s*["\']([^"\']+)["\']\s*,')
    # SparkConf().set("key", value)
    SPARK_CONF = re.compile(r'SparkConf\(\)(?:\.set\s*\(\s*["\']([^"\']+)["\'])+', re.DOTALL)

    def can_extract(self, ctx: ExtractionContext) -> bool:
        text_lower = ctx.text.lower()
        return "spark" in text_lower and "conf" in text_lower

    def extract(self, ctx: ExtractionContext) -> Generator[Union[Node, Edge], None, None]:
        seen = set()

        # spark.conf.get()
        for match in self.CONF_GET.finditer(ctx.text):
            key = match.group(1)
            if key in seen:
                continue
            seen.add(key)

            line = ctx.text[: match.start()].count("\n") + 1
            config_id = f"config:spark:{key}"

            yield Node(
                id=config_id,
                name=key,
                type=NodeType.CONFIG_KEY,
                path=str(ctx.file_path),
                metadata={
                    "config_type": "spark",
                    "line": line,
                },
            )

            yield Edge(
                source_id=ctx.file_id,
                target_id=config_id,
                type=RelationshipType.READS,
            )
