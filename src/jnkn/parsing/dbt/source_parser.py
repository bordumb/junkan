"""
dbt Source Parser.

Parses raw dbt project files (.sql, .yml) directly.
"""

from pathlib import Path
from typing import Generator, List, Union

from ...core.types import Edge, Node, NodeType, ScanMetadata
from ..base import (
    ExtractionContext,
    ExtractorRegistry,
    LanguageParser,
    ParserCapability,
    ParserContext,
)
from .extractors.columns import DbtColumnExtractor
from .extractors.jinja import JinjaExtractor
from .extractors.schema_yaml import SchemaYamlExtractor
from .extractors.sql_files import SQLFileExtractor


class DbtSourceParser(LanguageParser):
    """
    Parser for raw dbt source files.
    """

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._extractors = ExtractorRegistry()
        self._register_extractors()

    def _register_extractors(self) -> None:
        self._extractors.register(SQLFileExtractor())
        self._extractors.register(JinjaExtractor())
        self._extractors.register(DbtColumnExtractor())
        self._extractors.register(SchemaYamlExtractor())

    @property
    def name(self) -> str:
        return "dbt_source"

    @property
    def extensions(self) -> List[str]:
        return [".sql", ".yml", ".yaml"]

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.DEPENDENCIES,
            ParserCapability.ENV_VARS,
            ParserCapability.DATA_LINEAGE,
            ParserCapability.CONFIGS,
        ]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        """
        Check if file is part of a dbt project.
        """
        if file_path.suffix not in self.extensions:
            return False

        # Directory check using parts for robustness
        # Matches 'models', 'seeds', etc. anywhere in the path
        dbt_dirs = {"models", "seeds", "snapshots", "analyses", "macros"}

        # Check if any parent folder matches a dbt folder name
        # OR if the file is directly inside one of these (e.g. models/user.sql)
        for part in file_path.parts:
            if part in dbt_dirs:
                return True

        # Content check for files outside standard dirs (fallback)
        if content:
            try:
                text = content.decode("utf-8")
                return "{{ config" in text or "{{ ref" in text or "dbt_project.yml" in text
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
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception:
                return

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
            language="sql" if file_path.suffix == ".sql" else "yaml",
            file_hash=file_hash,
            metadata={"parser": "dbt_source"},
        )

        ctx = ExtractionContext(file_path=file_path, file_id=file_id, text=text, seen_ids=set())

        yield from self._extract_extractors(ctx)

    def _extract_extractors(self, ctx):
        yield from self._extractors.extract_all(ctx)


def create_dbt_source_parser(context: ParserContext | None = None) -> DbtSourceParser:
    return DbtSourceParser(context)
