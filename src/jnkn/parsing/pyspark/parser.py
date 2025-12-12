"""
PySpark Parser for jnkn.

This parser extracts data lineage information from PySpark code:
- Table reads (spark.read.table, spark.sql SELECT, etc.)
- Table writes (saveAsTable, insertInto, etc.)
- File reads/writes (parquet, delta, csv, etc.)
- DataFrame transformations and column usage

Designed for data engineering workflows where understanding
"what reads from what" and "what writes to what" is critical.

Supported Patterns:
- spark.read.table("schema.table")
- spark.table("schema.table")
- spark.sql("SELECT ... FROM table")
- spark.read.parquet("s3://path")
- spark.read.format("delta").load("path")
- df.write.saveAsTable("schema.table")
- df.write.insertInto("schema.table")
- df.write.parquet("s3://path")
"""

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Generator, List, Union

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import (
    LanguageParser,
    ParserCapability,
    ParserContext,
)

logger = logging.getLogger(__name__)


@dataclass
class TableReference:
    """Represents a reference to a table or data source."""

    name: str
    operation: str  # "read" or "write"
    pattern: str  # Which pattern detected it
    line: int
    source_type: str = "table"  # "table", "parquet", "delta", "csv", etc.

    def to_node_id(self) -> str:
        """Generate unique node ID for this table."""
        # Normalize table names: schema.table -> schema.table
        # S3 paths: s3://bucket/path -> s3:bucket/path
        normalized = self.name.replace("://", ":")
        return f"data:{normalized}"


class PySparkParser(LanguageParser):
    """
    PySpark parser for extracting data lineage.

    Features:
    - Detects table reads via multiple patterns
    - Detects table writes via multiple patterns
    - Extracts SQL queries and parses table references
    - Handles dynamic table names where possible
    - Tracks file-based data sources (parquet, delta, csv)
    """

    # ==========================================================================
    # Table READ patterns
    # ==========================================================================
    TABLE_READ_PATTERNS = [
        # spark.read.table("schema.table")
        (r'spark\.read\.table\s*\(\s*["\']([^"\']+)["\']', "spark.read.table"),
        # spark.table("schema.table")
        (r'spark\.table\s*\(\s*["\']([^"\']+)["\']', "spark.table"),
        # spark.read.format("X").load("path") - captures the path
        (
            r'spark\.read\.format\s*\([^)]+\).*?\.load\s*\(\s*["\']([^"\']+)["\']',
            "spark.read.format.load",
        ),
        # spark.read.parquet("path")
        (r'spark\.read\.parquet\s*\(\s*["\']([^"\']+)["\']', "spark.read.parquet"),
        # spark.read.csv("path")
        (r'spark\.read\.csv\s*\(\s*["\']([^"\']+)["\']', "spark.read.csv"),
        # spark.read.json("path")
        (r'spark\.read\.json\s*\(\s*["\']([^"\']+)["\']', "spark.read.json"),
        # spark.read.orc("path")
        (r'spark\.read\.orc\s*\(\s*["\']([^"\']+)["\']', "spark.read.orc"),
        # spark.read.jdbc(...) - extract table from properties
        (r'spark\.read\.jdbc\s*\([^,]+,\s*["\']([^"\']+)["\']', "spark.read.jdbc"),
        # DeltaTable.forPath(spark, "path")
        (r'DeltaTable\.forPath\s*\([^,]+,\s*["\']([^"\']+)["\']', "DeltaTable.forPath"),
        # DeltaTable.forName(spark, "schema.table")
        (r'DeltaTable\.forName\s*\([^,]+,\s*["\']([^"\']+)["\']', "DeltaTable.forName"),
    ]

    # ==========================================================================
    # Table WRITE patterns
    # ==========================================================================
    TABLE_WRITE_PATTERNS = [
        # df.write.saveAsTable("schema.table") - handles chained methods with whitespace
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*saveAsTable\s*\(\s*["\']([^"\']+)["\']',
            "write.saveAsTable",
        ),
        # df.write.insertInto("schema.table")
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*insertInto\s*\(\s*["\']([^"\']+)["\']',
            "write.insertInto",
        ),
        # df.write.parquet("path")
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*parquet\s*\(\s*["\']([^"\']+)["\']',
            "write.parquet",
        ),
        # df.write.csv("path")
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*csv\s*\(\s*["\']([^"\']+)["\']',
            "write.csv",
        ),
        # df.write.json("path")
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*json\s*\(\s*["\']([^"\']+)["\']',
            "write.json",
        ),
        # df.write.format("X").save("path") - generic save
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*save\s*\(\s*["\']([^"\']+)["\']',
            "write.save",
        ),
        # df.write.jdbc(...) - extract table
        (
            r'\.write\s*(?:\.\s*[a-zA-Z_]+\s*\([^)]*\)\s*)*\.\s*jdbc\s*\([^,]+,\s*["\']([^"\']+)["\']',
            "write.jdbc",
        ),
        # df.writeTo("schema.table").create()/append()/etc
        (r'\.writeTo\s*\(\s*["\']([^"\']+)["\']', "writeTo"),
    ]

    # ==========================================================================
    # SQL query patterns (for extracting tables from spark.sql())
    # ==========================================================================
    SPARK_SQL_PATTERN = re.compile(
        r'spark\.sql\s*\(\s*(?:f?["\'\"])\s*(.*?)\s*(?:["\'\"])\s*\)', re.DOTALL | re.IGNORECASE
    )

    # SQL FROM/JOIN clause table extraction
    SQL_TABLE_PATTERN = re.compile(
        r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)", re.IGNORECASE
    )

    # SQL INSERT INTO pattern
    SQL_INSERT_PATTERN = re.compile(
        r"INSERT\s+(?:INTO|OVERWRITE)\s+(?:TABLE\s+)?([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)",
        re.IGNORECASE,
    )

    # SQL CREATE TABLE AS SELECT
    SQL_CTAS_PATTERN = re.compile(
        r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:TEMP(?:ORARY)?\s+)?TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)",
        re.IGNORECASE,
    )

    # SQL MERGE INTO
    SQL_MERGE_PATTERN = re.compile(
        r"MERGE\s+INTO\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)", re.IGNORECASE
    )

    # SQL USING clause (source table in MERGE)
    SQL_USING_PATTERN = re.compile(
        r"USING\s+([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)", re.IGNORECASE
    )

    def __init__(self, context: ParserContext | None = None):
        super().__init__(context)
        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Compile patterns once
        self._read_patterns = [
            (re.compile(pattern, re.MULTILINE | re.DOTALL), name)
            for pattern, name in self.TABLE_READ_PATTERNS
        ]
        self._write_patterns = [
            (re.compile(pattern, re.MULTILINE | re.DOTALL), name)
            for pattern, name in self.TABLE_WRITE_PATTERNS
        ]

    @property
    def name(self) -> str:
        return "pyspark"

    @property
    def extensions(self) -> List[str]:
        return [".py"]

    @property
    def description(self) -> str:
        return "PySpark parser for data lineage extraction"

    def get_capabilities(self) -> List[ParserCapability]:
        return [
            ParserCapability.DATA_LINEAGE,
            ParserCapability.IMPORTS,
        ]

    def can_parse(self, file_path: Path, content: bytes | None = None) -> bool:
        """
        Determine if this file should be parsed as PySpark.

        Checks for:
        - .py extension
        - Contains PySpark imports or patterns
        """
        if file_path.suffix != ".py":
            return False

        if content is None:
            return True  # Assume yes if we can't check content

        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            return False

        # Check for PySpark indicators
        pyspark_indicators = [
            "from pyspark",
            "import pyspark",
            "SparkSession",
            "spark.read",
            "spark.sql",
            "spark.table",
            ".saveAsTable",
            "DeltaTable",
        ]

        return any(indicator in text for indicator in pyspark_indicators)

    def parse(
        self,
        file_path: Path,
        content: bytes,
    ) -> Generator[Union[Node, Edge], None, None]:
        """
        Parse a PySpark file and yield nodes and edges.

        Args:
            file_path: Path to the Python file
            content: File contents as bytes

        Yields:
            Node and Edge objects for discovered data lineage
        """
        # Create file node
        file_id = f"file://{file_path}"
        yield Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=str(file_path),
            language="python",
            metadata={"parser": "pyspark"},
        )

        # Decode content
        try:
            text = content.decode(self.context.encoding)
        except UnicodeDecodeError:
            try:
                text = content.decode("latin-1")
            except Exception as e:
                self._logger.error(f"Failed to decode {file_path}: {e}")
                return

        # Normalize backslash line continuations for better pattern matching
        # This handles multiline method chains like:
        #   df.write \
        #       .mode("overwrite") \
        #       .saveAsTable("table")
        normalized_text = text.replace("\\\n", " ")

        # Track seen tables to avoid duplicates
        seen_tables: Dict[str, str] = {}  # table_name -> operation

        # Extract table reads
        for table_ref in self._extract_table_reads(normalized_text):
            if table_ref.name in seen_tables:
                continue
            seen_tables[table_ref.name] = "read"

            yield from self._emit_table_reference(file_id, file_path, table_ref, "read")

        # Extract table writes
        for table_ref in self._extract_table_writes(normalized_text):
            if table_ref.name in seen_tables and seen_tables[table_ref.name] == "write":
                continue
            seen_tables[table_ref.name] = "write"

            yield from self._emit_table_reference(file_id, file_path, table_ref, "write")

        # Extract tables from SQL queries
        for table_ref in self._extract_sql_tables(normalized_text):
            if table_ref.name in seen_tables:
                continue
            seen_tables[table_ref.name] = table_ref.operation

            yield from self._emit_table_reference(
                file_id, file_path, table_ref, table_ref.operation
            )

    def _extract_table_reads(self, text: str) -> Generator[TableReference, None, None]:
        """Extract table read operations from code."""
        for pattern, pattern_name in self._read_patterns:
            for match in pattern.finditer(text):
                table_name = match.group(1)

                # Skip obviously invalid table names
                if not self._is_valid_table_name(table_name):
                    continue

                # Determine source type from pattern
                source_type = self._get_source_type(pattern_name)

                line = text[: match.start()].count("\n") + 1

                yield TableReference(
                    name=table_name,
                    operation="read",
                    pattern=pattern_name,
                    line=line,
                    source_type=source_type,
                )

    def _extract_table_writes(self, text: str) -> Generator[TableReference, None, None]:
        """Extract table write operations from code."""
        for pattern, pattern_name in self._write_patterns:
            for match in pattern.finditer(text):
                table_name = match.group(1)

                # Skip obviously invalid table names
                if not self._is_valid_table_name(table_name):
                    continue

                # Determine source type from pattern
                source_type = self._get_source_type(pattern_name)

                line = text[: match.start()].count("\n") + 1

                yield TableReference(
                    name=table_name,
                    operation="write",
                    pattern=pattern_name,
                    line=line,
                    source_type=source_type,
                )

    def _extract_sql_tables(self, text: str) -> Generator[TableReference, None, None]:
        """Extract table references from spark.sql() calls."""
        for sql_match in self.SPARK_SQL_PATTERN.finditer(text):
            sql_query = sql_match.group(1)
            sql_line = text[: sql_match.start()].count("\n") + 1

            # Extract tables from FROM/JOIN clauses (reads)
            for table_match in self.SQL_TABLE_PATTERN.finditer(sql_query):
                table_name = table_match.group(1)
                if self._is_valid_table_name(table_name):
                    yield TableReference(
                        name=table_name,
                        operation="read",
                        pattern="spark.sql.FROM",
                        line=sql_line,
                        source_type="table",
                    )

            # Extract tables from INSERT INTO (writes)
            for insert_match in self.SQL_INSERT_PATTERN.finditer(sql_query):
                table_name = insert_match.group(1)
                if self._is_valid_table_name(table_name):
                    yield TableReference(
                        name=table_name,
                        operation="write",
                        pattern="spark.sql.INSERT",
                        line=sql_line,
                        source_type="table",
                    )

            # Extract tables from CREATE TABLE AS SELECT (writes)
            for ctas_match in self.SQL_CTAS_PATTERN.finditer(sql_query):
                table_name = ctas_match.group(1)
                if self._is_valid_table_name(table_name):
                    yield TableReference(
                        name=table_name,
                        operation="write",
                        pattern="spark.sql.CTAS",
                        line=sql_line,
                        source_type="table",
                    )

            # Extract tables from MERGE INTO (writes)
            for merge_match in self.SQL_MERGE_PATTERN.finditer(sql_query):
                table_name = merge_match.group(1)
                if self._is_valid_table_name(table_name):
                    yield TableReference(
                        name=table_name,
                        operation="write",
                        pattern="spark.sql.MERGE",
                        line=sql_line,
                        source_type="table",
                    )

            # Extract tables from USING clause (source table in MERGE - reads)
            for using_match in self.SQL_USING_PATTERN.finditer(sql_query):
                table_name = using_match.group(1)
                if self._is_valid_table_name(table_name):
                    yield TableReference(
                        name=table_name,
                        operation="read",
                        pattern="spark.sql.USING",
                        line=sql_line,
                        source_type="table",
                    )

    def _emit_table_reference(
        self,
        file_id: str,
        file_path: Path,
        table_ref: TableReference,
        operation: str,
    ) -> Generator[Union[Node, Edge], None, None]:
        """Emit nodes and edges for a table reference."""
        table_id = table_ref.to_node_id()

        # Create table/data asset node
        yield Node(
            id=table_id,
            name=table_ref.name,
            type=NodeType.DATA_ASSET,
            metadata={
                "source_type": table_ref.source_type,
                "pattern": table_ref.pattern,
                "file": str(file_path),
                "line": table_ref.line,
            },
        )

        # Create edge based on operation
        if operation == "read":
            yield Edge(
                source_id=file_id,
                target_id=table_id,
                type=RelationshipType.READS,
                metadata={
                    "pattern": table_ref.pattern,
                    "line": table_ref.line,
                },
            )
        else:  # write
            yield Edge(
                source_id=file_id,
                target_id=table_id,
                type=RelationshipType.WRITES,
                metadata={
                    "pattern": table_ref.pattern,
                    "line": table_ref.line,
                },
            )

    def _is_valid_table_name(self, name: str) -> bool:
        """
        Check if a string looks like a valid table name.

        Filters out:
        - Empty strings
        - Pure variables (no schema/path indicators)
        - Common false positives
        """
        if not name or len(name) < 2:
            return False

        # Skip common false positives
        false_positives = {
            "path",
            "table",
            "file",
            "data",
            "output",
            "input",
            "source",
            "target",
            "temp",
            "tmp",
        }
        if name.lower() in false_positives:
            return False

        # Skip if it's clearly a variable (no dots, no slashes, all lowercase single word)
        if "." not in name and "/" not in name and name.islower() and "_" not in name:
            return False

        # Accept paths (s3://, gs://, hdfs://, etc.)
        if "://" in name:
            return True

        # Accept schema.table format
        if "." in name:
            return True

        # Accept paths with slashes
        if "/" in name:
            return True

        # Accept names with underscores (likely real tables)
        if "_" in name:
            return True

        # Accept SCREAMING_CASE (likely constants)
        if name.isupper():
            return True

        return True

    def _get_source_type(self, pattern_name: str) -> str:
        """Determine the data source type from the pattern name."""
        if "parquet" in pattern_name:
            return "parquet"
        elif "delta" in pattern_name.lower() or "Delta" in pattern_name:
            return "delta"
        elif "csv" in pattern_name:
            return "csv"
        elif "json" in pattern_name:
            return "json"
        elif "orc" in pattern_name:
            return "orc"
        elif "jdbc" in pattern_name:
            return "jdbc"
        else:
            return "table"


def create_pyspark_parser(context: ParserContext | None = None) -> PySparkParser:
    """Factory function to create a PySpark parser."""
    return PySparkParser(context)
