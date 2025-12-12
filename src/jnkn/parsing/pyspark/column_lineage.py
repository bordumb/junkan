"""
Column-Level Lineage Extractor for PySpark.

Extracts column references from:
1. SQL strings (using sqlglot)
2. DataFrame method chains (.select, .filter, .withColumn, etc.)
3. Variable references (best-effort resolution)

Usage:
    extractor = ColumnLineageExtractor()
    result = extractor.extract(source_code)

    # Access results
    result.columns_read      # All columns read
    result.columns_written   # All columns written
    result.lineage           # Output → Source mappings
    result.dynamic_refs      # Unresolved dynamic references
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Tuple


class ColumnContext(Enum):
    """Where a column reference appears."""

    SELECT = "select"
    FILTER = "filter"
    GROUPBY = "groupby"
    ORDERBY = "orderby"
    JOIN = "join"
    AGG = "agg"
    TRANSFORM = "transform"
    WRITE = "write"
    UNKNOWN = "unknown"


class Confidence(Enum):
    """Confidence level for extracted column."""

    HIGH = 3  # Literal string, SQL parsing
    MEDIUM = 2  # Resolved variable
    LOW = 1  # Partial resolution
    UNKNOWN = 0  # Dynamic/unresolvable

    @property
    def label(self) -> str:
        return self.name.lower()


@dataclass
class ColumnRef:
    """A reference to a column in source code."""

    column: str
    table: str | None = None
    alias: str | None = None
    context: ColumnContext = ColumnContext.UNKNOWN
    line_number: int = 0
    confidence: Confidence = Confidence.HIGH
    transform: str | None = None  # sum, avg, concat, etc.

    @property
    def qualified_name(self) -> str:
        if self.table:
            return f"{self.table}.{self.column}"
        return self.column

    def to_dict(self) -> Dict[str, Any]:
        return {
            "column": self.column,
            "table": self.table,
            "alias": self.alias,
            "context": self.context.value,
            "line": self.line_number,
            "confidence": self.confidence.label,
            "transform": self.transform,
        }


@dataclass
class ColumnLineageMapping:
    """Maps output column to source columns."""

    output_column: str
    output_table: str | None
    source_columns: List[ColumnRef]
    transform: str | None = None
    confidence: Confidence = Confidence.HIGH

    def to_dict(self) -> Dict[str, Any]:
        return {
            "output": f"{self.output_table}.{self.output_column}"
            if self.output_table
            else self.output_column,
            "sources": [s.to_dict() for s in self.source_columns],
            "transform": self.transform,
            "confidence": self.confidence.label,
        }


@dataclass
class DynamicReference:
    """A column reference that couldn't be resolved."""

    pattern: str
    line_number: int
    variable_name: str | None = None
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pattern": self.pattern,
            "line": self.line_number,
            "variable": self.variable_name,
            "note": self.note,
        }


@dataclass
class ColumnLineageResult:
    """Complete column lineage extraction result."""

    file_path: str = ""
    columns_read: List[ColumnRef] = field(default_factory=list)
    columns_written: List[ColumnRef] = field(default_factory=list)
    lineage: List[ColumnLineageMapping] = field(default_factory=list)
    dynamic_refs: List[DynamicReference] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file": self.file_path,
            "columns_read": [c.to_dict() for c in self.columns_read],
            "columns_written": [c.to_dict() for c in self.columns_written],
            "lineage": [l.to_dict() for l in self.lineage],
            "dynamic_refs": [d.to_dict() for d in self.dynamic_refs],
            "stats": {
                "total_columns_read": len(self.columns_read),
                "total_columns_written": len(self.columns_written),
                "lineage_mappings": len(self.lineage),
                "dynamic_references": len(self.dynamic_refs),
            },
        }


class ColumnLineageExtractor:
    """
    Extracts column-level lineage from PySpark code.

    Handles:
    - SQL strings (spark.sql("..."))
    - DataFrame methods (.select, .filter, .withColumn, etc.)
    - col() and F.col() references
    - Variable resolution (best-effort)
    """

    # Aggregation functions that transform columns
    AGG_FUNCTIONS = {
        "sum",
        "avg",
        "mean",
        "count",
        "min",
        "max",
        "first",
        "last",
        "collect_list",
        "collect_set",
        "stddev",
        "variance",
        "approx_count_distinct",
        "countDistinct",
        "sumDistinct",
    }

    # Transform functions
    TRANSFORM_FUNCTIONS = {
        "concat",
        "concat_ws",
        "substring",
        "trim",
        "lower",
        "upper",
        "to_date",
        "to_timestamp",
        "date_format",
        "datediff",
        "round",
        "floor",
        "ceil",
        "abs",
        "when",
        "coalesce",
        "ifnull",
        "nullif",
        "split",
        "explode",
        "array",
        "struct",
        "cast",
        "lit",
    }

    def __init__(self):
        self._variables: Dict[str, Any] = {}  # Track variable assignments
        self._current_line = 0

    def extract(self, source_code: str, file_path: str = "") -> ColumnLineageResult:
        """
        Extract column-level lineage from PySpark source code.

        Args:
            source_code: Python source code containing PySpark
            file_path: Path to source file (for reporting)

        Returns:
            ColumnLineageResult with all extracted column references
        """
        result = ColumnLineageResult(file_path=file_path)

        # Normalize line continuations
        normalized = source_code.replace("\\\n", " ")
        lines = normalized.split("\n")

        # Phase 1: Extract variable assignments
        self._extract_variables(source_code)

        # Phase 2: Extract from SQL strings
        sql_refs = self._extract_from_sql(normalized, lines)
        result.columns_read.extend(sql_refs)

        # Phase 3: Extract from DataFrame methods
        df_refs, df_writes, df_dynamic = self._extract_from_dataframe_methods(normalized, lines)
        result.columns_read.extend(df_refs)
        result.columns_written.extend(df_writes)
        result.dynamic_refs.extend(df_dynamic)

        # Phase 4: Build lineage mappings
        result.lineage = self._build_lineage_mappings(result.columns_read, result.columns_written)

        # Deduplicate
        result.columns_read = self._deduplicate_columns(result.columns_read)
        result.columns_written = self._deduplicate_columns(result.columns_written)

        return result

    # =========================================================================
    # Variable Extraction
    # =========================================================================

    def _extract_variables(self, source_code: str) -> None:
        """Extract variable assignments for column resolution."""
        self._variables = {}

        # Pattern: var = ["col1", "col2", ...]
        list_pattern = r'(\w+)\s*=\s*\[((?:["\'][^"\']+["\'](?:\s*,\s*)?)+)\]'

        for match in re.finditer(list_pattern, source_code):
            var_name = match.group(1)
            list_content = match.group(2)

            # Extract string values
            strings = re.findall(r'["\']([^"\']+)["\']', list_content)
            if strings:
                self._variables[var_name] = strings

        # Pattern: var = "single_value"
        string_pattern = r'(\w+)\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(string_pattern, source_code):
            var_name = match.group(1)
            value = match.group(2)
            # Only store if looks like a column name
            if re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", value):
                self._variables[var_name] = value

    def _resolve_variable(self, var_name: str) -> Tuple[List[str] | None, Confidence]:
        """Try to resolve a variable to column names."""
        if var_name in self._variables:
            value = self._variables[var_name]
            if isinstance(value, list):
                return value, Confidence.MEDIUM
            else:
                return [value], Confidence.MEDIUM
        return None, Confidence.UNKNOWN

    # =========================================================================
    # SQL String Extraction
    # =========================================================================

    def _extract_from_sql(self, source: str, lines: List[str]) -> List[ColumnRef]:
        """Extract column references from SQL strings."""
        columns = []

        # Find spark.sql("...") calls
        sql_pattern = r'spark\.sql\s*\(\s*(?:f?["\']|\"{3}|f\"{3})(.*?)(?:["\']|\"{3})\s*\)'

        for match in re.finditer(sql_pattern, source, re.DOTALL):
            sql_string = match.group(1)
            line_num = source[: match.start()].count("\n") + 1

            # Try sqlglot first, fall back to regex
            try:
                sql_columns = self._parse_sql_with_sqlglot(sql_string, line_num)
                columns.extend(sql_columns)
            except Exception:
                sql_columns = self._parse_sql_with_regex(sql_string, line_num)
                columns.extend(sql_columns)

        return columns

    def _parse_sql_with_sqlglot(self, sql: str, line_num: int) -> List[ColumnRef]:
        """Parse SQL using sqlglot for accurate extraction."""
        columns = []

        try:
            import sqlglot
            from sqlglot import exp
        except ImportError:
            return self._parse_sql_with_regex(sql, line_num)

        try:
            parsed = sqlglot.parse_one(sql)
        except Exception:
            return self._parse_sql_with_regex(sql, line_num)

        # Extract tables for context
        tables = {}
        for table in parsed.find_all(exp.Table):
            table_name = table.name
            alias = table.alias if hasattr(table, "alias") and table.alias else table_name
            tables[alias] = table_name

        # Extract SELECT columns
        for select in parsed.find_all(exp.Select):
            for expr in select.expressions:
                col_refs = self._extract_columns_from_sqlglot_expr(
                    expr, tables, line_num, ColumnContext.SELECT
                )
                columns.extend(col_refs)

        # Extract WHERE columns
        for where in parsed.find_all(exp.Where):
            col_refs = self._extract_columns_from_sqlglot_expr(
                where, tables, line_num, ColumnContext.FILTER
            )
            columns.extend(col_refs)

        # Extract JOIN columns
        for join in parsed.find_all(exp.Join):
            if join.args.get("on"):
                col_refs = self._extract_columns_from_sqlglot_expr(
                    join.args["on"], tables, line_num, ColumnContext.JOIN
                )
                columns.extend(col_refs)

        # Extract GROUP BY columns
        for group in parsed.find_all(exp.Group):
            for expr in group.expressions:
                col_refs = self._extract_columns_from_sqlglot_expr(
                    expr, tables, line_num, ColumnContext.GROUPBY
                )
                columns.extend(col_refs)

        return columns

    def _extract_columns_from_sqlglot_expr(
        self, expr, tables: Dict[str, str], line_num: int, context: ColumnContext
    ) -> List[ColumnRef]:
        """Extract column references from a sqlglot expression."""
        columns = []

        try:
            from sqlglot import exp
        except ImportError:
            return columns

        # Find all column references
        for col in expr.find_all(exp.Column):
            col_name = col.name
            table_alias = col.table if hasattr(col, "table") and col.table else None
            table_name = tables.get(table_alias, table_alias) if table_alias else None

            # Check for alias
            alias = None
            if hasattr(col, "parent") and isinstance(col.parent, exp.Alias):
                alias = col.parent.alias

            # Check for aggregation
            transform = None
            if hasattr(col, "parent"):
                parent = col.parent
                if isinstance(parent, (exp.Sum, exp.Avg, exp.Count, exp.Min, exp.Max)):
                    transform = type(parent).__name__.lower()

            columns.append(
                ColumnRef(
                    column=col_name,
                    table=table_name,
                    alias=alias,
                    context=context,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                    transform=transform,
                )
            )

        return columns

    def _parse_sql_with_regex(self, sql: str, line_num: int) -> List[ColumnRef]:
        """Fallback regex-based SQL parsing."""
        columns = []

        # Normalize whitespace
        sql_normalized = " ".join(sql.split())

        # Extract FROM/JOIN tables for context
        tables = {}
        table_pattern = r"(?:FROM|JOIN)\s+(\w+(?:\.\w+)?)\s*(?:(?:AS\s+)?(\w+))?"
        for match in re.finditer(table_pattern, sql_normalized, re.IGNORECASE):
            table = match.group(1)
            alias = match.group(2) or table.split(".")[-1]
            tables[alias.lower()] = table

        # Extract SELECT columns
        select_match = re.search(
            r"SELECT\s+(.*?)\s+FROM", sql_normalized, re.IGNORECASE | re.DOTALL
        )
        if select_match:
            select_clause = select_match.group(1)

            # Skip SELECT *
            if select_clause.strip() != "*":
                # Split by comma (careful with functions)
                col_exprs = self._split_sql_columns(select_clause)

                for expr in col_exprs:
                    col_refs = self._parse_sql_column_expr(
                        expr, tables, line_num, ColumnContext.SELECT
                    )
                    columns.extend(col_refs)

        # Extract WHERE columns
        where_match = re.search(
            r"WHERE\s+(.*?)(?:GROUP|ORDER|LIMIT|$)", sql_normalized, re.IGNORECASE
        )
        if where_match:
            where_clause = where_match.group(1)
            col_refs = self._extract_columns_from_sql_clause(
                where_clause, tables, line_num, ColumnContext.FILTER
            )
            columns.extend(col_refs)

        # Extract JOIN ON columns
        join_on_pattern = r"JOIN\s+\w+(?:\.\w+)?(?:\s+(?:AS\s+)?\w+)?\s+ON\s+(.*?)(?:WHERE|JOIN|GROUP|ORDER|LIMIT|$)"
        for match in re.finditer(join_on_pattern, sql_normalized, re.IGNORECASE):
            on_clause = match.group(1)
            col_refs = self._extract_columns_from_sql_clause(
                on_clause, tables, line_num, ColumnContext.JOIN
            )
            columns.extend(col_refs)

        # Extract GROUP BY columns
        groupby_match = re.search(
            r"GROUP\s+BY\s+(.*?)(?:HAVING|ORDER|LIMIT|$)", sql_normalized, re.IGNORECASE
        )
        if groupby_match:
            groupby_clause = groupby_match.group(1)
            col_refs = self._extract_columns_from_sql_clause(
                groupby_clause, tables, line_num, ColumnContext.GROUPBY
            )
            columns.extend(col_refs)

        return columns

    def _split_sql_columns(self, select_clause: str) -> List[str]:
        """Split SELECT clause by commas, respecting parentheses."""
        columns = []
        current = []
        depth = 0

        for char in select_clause:
            if char == "(":
                depth += 1
                current.append(char)
            elif char == ")":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                columns.append("".join(current).strip())
                current = []
            else:
                current.append(char)

        if current:
            columns.append("".join(current).strip())

        return columns

    def _parse_sql_column_expr(
        self, expr: str, tables: Dict[str, str], line_num: int, context: ColumnContext
    ) -> List[ColumnRef]:
        """Parse a single SQL column expression."""
        columns = []

        # Check for alias
        alias_match = re.search(r"\s+(?:AS\s+)?(\w+)\s*$", expr, re.IGNORECASE)
        alias = alias_match.group(1) if alias_match else None

        # Check for aggregation function
        agg_match = re.match(r"(\w+)\s*\((.*)\)", expr.strip(), re.IGNORECASE)
        transform = None
        inner_expr = expr

        if agg_match:
            func_name = agg_match.group(1).lower()
            if func_name in self.AGG_FUNCTIONS:
                transform = func_name
                inner_expr = agg_match.group(2)
            elif func_name in self.TRANSFORM_FUNCTIONS:
                transform = func_name
                inner_expr = agg_match.group(2)

        # Extract column references (table.column or just column)
        col_pattern = r"(?:(\w+)\.)?(\w+)"
        for match in re.finditer(col_pattern, inner_expr):
            table_alias = match.group(1)
            col_name = match.group(2)

            # Skip keywords and literals
            if col_name.upper() in ("AS", "AND", "OR", "NOT", "NULL", "TRUE", "FALSE"):
                continue
            if col_name.isdigit():
                continue

            table_name = tables.get(table_alias.lower(), table_alias) if table_alias else None

            columns.append(
                ColumnRef(
                    column=col_name,
                    table=table_name,
                    alias=alias,
                    context=context,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                    transform=transform,
                )
            )

            # Only first column gets the alias
            alias = None

        return columns

    def _extract_columns_from_sql_clause(
        self, clause: str, tables: Dict[str, str], line_num: int, context: ColumnContext
    ) -> List[ColumnRef]:
        """Extract column references from a SQL clause (WHERE, GROUP BY, etc.)."""
        columns = []

        # Remove string literals to avoid false positives
        # Replace 'value' and "value" with placeholder
        clause_clean = re.sub(r"'[^']*'", "''", clause)
        clause_clean = re.sub(r'"[^"]*"', '""', clause_clean)

        # Pattern: table.column or just column
        col_pattern = r"(?:(\w+)\.)?(\w+)"

        for match in re.finditer(col_pattern, clause_clean):
            table_alias = match.group(1)
            col_name = match.group(2)

            # Skip SQL keywords and operators
            skip_words = {
                "AND",
                "OR",
                "NOT",
                "IN",
                "IS",
                "NULL",
                "LIKE",
                "BETWEEN",
                "TRUE",
                "FALSE",
                "ASC",
                "DESC",
                "LIMIT",
                "OFFSET",
                "CASE",
                "WHEN",
                "THEN",
                "ELSE",
                "END",
                "AS",
            }
            if col_name.upper() in skip_words:
                continue
            if col_name.isdigit():
                continue
            # Skip if it's an empty placeholder from string removal
            if col_name == "":
                continue

            table_name = tables.get(table_alias.lower(), table_alias) if table_alias else None

            columns.append(
                ColumnRef(
                    column=col_name,
                    table=table_name,
                    context=context,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                )
            )

        return columns

    # =========================================================================
    # DataFrame Method Extraction
    # =========================================================================

    def _extract_from_dataframe_methods(
        self, source: str, lines: List[str]
    ) -> Tuple[List[ColumnRef], List[ColumnRef], List[DynamicReference]]:
        """Extract columns from DataFrame method calls."""
        columns_read = []
        columns_written = []
        dynamic_refs = []

        # .select() - columns being selected
        select_cols, select_dynamic = self._extract_select_columns(source)
        columns_read.extend(select_cols)
        dynamic_refs.extend(select_dynamic)

        # .filter() / .where() - columns being filtered
        filter_cols, filter_dynamic = self._extract_filter_columns(source)
        columns_read.extend(filter_cols)
        dynamic_refs.extend(filter_dynamic)

        # .withColumn() - new column + source columns
        with_cols_read, with_cols_written = self._extract_withcolumn(source)
        columns_read.extend(with_cols_read)
        columns_written.extend(with_cols_written)

        # .groupBy() - grouping columns
        groupby_cols, groupby_dynamic = self._extract_groupby_columns(source)
        columns_read.extend(groupby_cols)
        dynamic_refs.extend(groupby_dynamic)

        # .agg() - aggregation columns
        agg_cols, agg_written = self._extract_agg_columns(source)
        columns_read.extend(agg_cols)
        columns_written.extend(agg_written)

        # .join() - join key columns
        join_cols = self._extract_join_columns(source)
        columns_read.extend(join_cols)

        # .orderBy() / .sort() - ordering columns
        order_cols, order_dynamic = self._extract_orderby_columns(source)
        columns_read.extend(order_cols)
        dynamic_refs.extend(order_dynamic)

        return columns_read, columns_written, dynamic_refs

    def _extract_select_columns(
        self, source: str
    ) -> Tuple[List[ColumnRef], List[DynamicReference]]:
        """Extract columns from .select() calls."""
        columns = []
        dynamic = []

        # Pattern: .select("col1", "col2") or .select(col("col1"), col("col2"))
        select_pattern = r"\.select\s*\((.*?)\)"

        for match in re.finditer(select_pattern, source, re.DOTALL):
            args = match.group(1)
            line_num = source[: match.start()].count("\n") + 1

            cols, dyn = self._parse_column_args(args, line_num, ColumnContext.SELECT)
            columns.extend(cols)
            dynamic.extend(dyn)

        return columns, dynamic

    def _extract_filter_columns(
        self, source: str
    ) -> Tuple[List[ColumnRef], List[DynamicReference]]:
        """Extract columns from .filter() and .where() calls."""
        columns = []
        dynamic = []

        # Pattern: .filter(col("status") == "active") or .where(...)
        filter_pattern = r"\.(?:filter|where)\s*\((.*?)\)(?=\s*\.|\s*$|\s*\)|\s*\n)"

        for match in re.finditer(filter_pattern, source, re.DOTALL):
            args = match.group(1)
            line_num = source[: match.start()].count("\n") + 1

            # Extract col() references only - not the comparison values
            col_refs = self._extract_col_function_refs(args, line_num, ColumnContext.FILTER)
            columns.extend(col_refs)

            # Check for dynamic variable usage (but not string literals)
            # Pattern: col("x") == variable (where variable is not a string literal)
            var_pattern = r'col\(["\'][^"\']+["\']\)\s*[=!<>]+\s*([a-zA-Z_]\w*)\s*(?:\)|$|,)'
            for var_match in re.finditer(var_pattern, args):
                var_name = var_match.group(1)
                # Skip if it's a string literal or known constant
                if var_name not in self._variables and var_name not in ("True", "False", "None"):
                    dynamic.append(
                        DynamicReference(
                            pattern=match.group(0)[:50] + "..."
                            if len(match.group(0)) > 50
                            else match.group(0),
                            line_number=line_num,
                            variable_name=var_name,
                            note=f"Filter value from variable '{var_name}'",
                        )
                    )

        return columns, dynamic

    def _extract_withcolumn(self, source: str) -> Tuple[List[ColumnRef], List[ColumnRef]]:
        """Extract columns from .withColumn() calls."""
        columns_read = []
        columns_written = []

        # Pattern: .withColumn("new_col", expr)
        pattern = r'\.withColumn\s*\(\s*["\'](\w+)["\']\s*,\s*(.*?)\s*\)(?=\s*\.|\s*$)'

        for match in re.finditer(pattern, source, re.DOTALL):
            new_col = match.group(1)
            expr = match.group(2)
            line_num = source[: match.start()].count("\n") + 1

            # Output column
            columns_written.append(
                ColumnRef(
                    column=new_col,
                    context=ColumnContext.TRANSFORM,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                )
            )

            # Source columns from expression
            source_cols = self._extract_col_function_refs(expr, line_num, ColumnContext.TRANSFORM)
            columns_read.extend(source_cols)

        return columns_read, columns_written

    def _extract_groupby_columns(
        self, source: str
    ) -> Tuple[List[ColumnRef], List[DynamicReference]]:
        """Extract columns from .groupBy() calls."""
        columns = []
        dynamic = []

        pattern = r"\.groupBy\s*\((.*?)\)"

        for match in re.finditer(pattern, source, re.DOTALL):
            args = match.group(1)
            line_num = source[: match.start()].count("\n") + 1

            cols, dyn = self._parse_column_args(args, line_num, ColumnContext.GROUPBY)
            columns.extend(cols)
            dynamic.extend(dyn)

        return columns, dynamic

    def _extract_agg_columns(self, source: str) -> Tuple[List[ColumnRef], List[ColumnRef]]:
        """Extract columns from .agg() calls."""
        columns_read = []
        columns_written = []

        # Normalize source to help with multiline matching
        normalized = source.replace("\\\n", " ")

        # Pattern for .agg() - capture content between parentheses
        # Use a simple approach: find .agg( and then balance parentheses
        agg_starts = [m.start() for m in re.finditer(r"\.agg\s*\(", normalized)]

        for start in agg_starts:
            # Find matching closing paren
            paren_start = normalized.index("(", start)
            depth = 1
            pos = paren_start + 1
            while pos < len(normalized) and depth > 0:
                if normalized[pos] == "(":
                    depth += 1
                elif normalized[pos] == ")":
                    depth -= 1
                pos += 1

            if depth == 0:
                args = normalized[paren_start + 1 : pos - 1]
                line_num = normalized[:start].count("\n") + 1

                # Find aggregation expressions: sum("col").alias("name")
                # Pattern handles: sum("col"), F.sum("col"), sum(col("x")), sum("col").alias("name")
                agg_pattern = r'(?:F\.)?(\w+)\s*\(\s*(?:["\']([^"\']+)["\']|col\s*\(\s*["\']([^"\']+)["\']\s*\))\s*\)(?:\s*\.\s*alias\s*\(\s*["\']([^"\']+)["\']\s*\))?'

                for agg_match in re.finditer(agg_pattern, args):
                    func = agg_match.group(1).lower()
                    col_name = agg_match.group(2) or agg_match.group(3)
                    alias = agg_match.group(4)

                    if col_name and col_name != "*":
                        # Source column
                        columns_read.append(
                            ColumnRef(
                                column=col_name,
                                context=ColumnContext.AGG,
                                line_number=line_num,
                                confidence=Confidence.HIGH,
                                transform=func if func in self.AGG_FUNCTIONS else None,
                            )
                        )

                    # Output column
                    if alias:
                        columns_written.append(
                            ColumnRef(
                                column=alias,
                                context=ColumnContext.AGG,
                                line_number=line_num,
                                confidence=Confidence.HIGH,
                                transform=func if func in self.AGG_FUNCTIONS else None,
                            )
                        )
                    elif col_name:
                        # Default name is function(column)
                        columns_written.append(
                            ColumnRef(
                                column=f"{func}({col_name})",
                                context=ColumnContext.AGG,
                                line_number=line_num,
                                confidence=Confidence.HIGH,
                                transform=func if func in self.AGG_FUNCTIONS else None,
                            )
                        )

        return columns_read, columns_written

    def _extract_join_columns(self, source: str) -> List[ColumnRef]:
        """Extract columns from .join() calls."""
        columns = []

        # Pattern: .join(other_df, "key") or .join(other_df, ["key1", "key2"])
        # or .join(other_df, col("a") == col("b"))
        pattern = (
            r'\.join\s*\([^,]+,\s*(.*?)(?:,\s*["\'](?:inner|left|right|outer|cross)["\'])?\s*\)'
        )

        for match in re.finditer(pattern, source, re.DOTALL):
            args = match.group(1)
            line_num = source[: match.start()].count("\n") + 1

            # String key(s)
            string_keys = re.findall(r'["\'](\w+)["\']', args)
            for key in string_keys:
                columns.append(
                    ColumnRef(
                        column=key,
                        context=ColumnContext.JOIN,
                        line_number=line_num,
                        confidence=Confidence.HIGH,
                    )
                )

            # col() expressions
            col_refs = self._extract_col_function_refs(args, line_num, ColumnContext.JOIN)
            columns.extend(col_refs)

        return columns

    def _extract_orderby_columns(
        self, source: str
    ) -> Tuple[List[ColumnRef], List[DynamicReference]]:
        """Extract columns from .orderBy() and .sort() calls."""
        columns = []
        dynamic = []

        pattern = r"\.(?:orderBy|sort)\s*\((.*?)\)"

        for match in re.finditer(pattern, source, re.DOTALL):
            args = match.group(1)
            line_num = source[: match.start()].count("\n") + 1

            cols, dyn = self._parse_column_args(args, line_num, ColumnContext.ORDERBY)
            columns.extend(cols)
            dynamic.extend(dyn)

        return columns, dynamic

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _parse_column_args(
        self, args: str, line_num: int, context: ColumnContext
    ) -> Tuple[List[ColumnRef], List[DynamicReference]]:
        """Parse column arguments from a method call."""
        columns = []
        dynamic = []

        # String literals: "col1", "col2"
        string_cols = re.findall(r'["\'](\w+)["\']', args)
        for col in string_cols:
            columns.append(
                ColumnRef(
                    column=col,
                    context=context,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                )
            )

        # col() function calls
        col_refs = self._extract_col_function_refs(args, line_num, context)
        columns.extend(col_refs)

        # Check for variable references
        # Pattern: .select(var_name) or .select(*var_name)
        var_pattern = r'(?<!["\'])\b([a-zA-Z_]\w*)\b(?!["\'])'

        for var_match in re.finditer(var_pattern, args):
            var_name = var_match.group(1)

            # Skip known functions and keywords
            skip = {"col", "F", "lit", "asc", "desc", "when", "otherwise", "alias"}
            skip.update(self.AGG_FUNCTIONS)
            skip.update(self.TRANSFORM_FUNCTIONS)

            if var_name in skip:
                continue

            # Try to resolve variable
            resolved, confidence = self._resolve_variable(var_name)

            if resolved:
                for col in resolved:
                    columns.append(
                        ColumnRef(
                            column=col,
                            context=context,
                            line_number=line_num,
                            confidence=confidence,
                        )
                    )
            elif not var_name.startswith("_"):
                # Unresolved variable
                dynamic.append(
                    DynamicReference(
                        pattern=f".{context.value}({args})",
                        line_number=line_num,
                        variable_name=var_name,
                        note=f"Columns from variable '{var_name}'",
                    )
                )

        return columns, dynamic

    def _extract_col_function_refs(
        self, expr: str, line_num: int, context: ColumnContext
    ) -> List[ColumnRef]:
        """Extract column references from col() and F.col() calls."""
        columns = []

        # Pattern: col("name") or F.col("name")
        col_pattern = r'(?:F\.)?col\s*\(\s*["\'](\w+)["\']\s*\)'

        for match in re.finditer(col_pattern, expr):
            col_name = match.group(1)
            columns.append(
                ColumnRef(
                    column=col_name,
                    context=context,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                )
            )

        # Also check df["column"] syntax
        bracket_pattern = r'\w+\s*\[\s*["\'](\w+)["\']\s*\]'

        for match in re.finditer(bracket_pattern, expr):
            col_name = match.group(1)
            columns.append(
                ColumnRef(
                    column=col_name,
                    context=context,
                    line_number=line_num,
                    confidence=Confidence.HIGH,
                )
            )

        return columns

    def _deduplicate_columns(self, columns: List[ColumnRef]) -> List[ColumnRef]:
        """Remove duplicate column references, keeping unique by column+table+context+line."""
        seen = set()
        unique = []

        for col in columns:
            # Include line number in key to preserve columns from different locations
            key = (col.column, col.table, col.context, col.line_number)
            if key not in seen:
                seen.add(key)
                unique.append(col)

        return unique

    def _build_lineage_mappings(
        self, columns_read: List[ColumnRef], columns_written: List[ColumnRef]
    ) -> List[ColumnLineageMapping]:
        """Build lineage mappings from read/written columns."""
        mappings = []

        # Group written columns with their potential sources
        for written in columns_written:
            # Find source columns from the SAME line only (strict matching)
            sources = [
                r
                for r in columns_read
                if r.line_number == written.line_number and r.context == written.context
            ]

            # If no exact match, look for nearby in same context
            if not sources:
                sources = [
                    r
                    for r in columns_read
                    if r.context == written.context
                    and abs(r.line_number - written.line_number) <= 1
                ]

            if sources:
                mappings.append(
                    ColumnLineageMapping(
                        output_column=written.column,
                        output_table=written.table,
                        source_columns=sources,
                        transform=written.transform,
                        confidence=min(sources, key=lambda s: s.confidence.value).confidence,
                    )
                )

        return mappings


# =============================================================================
# Convenience Function
# =============================================================================


def extract_column_lineage(source_code: str, file_path: str = "") -> ColumnLineageResult:
    """
    Extract column-level lineage from PySpark source code.

    Args:
        source_code: Python source code containing PySpark
        file_path: Optional file path for reporting

    Returns:
        ColumnLineageResult with all extracted information
    """
    extractor = ColumnLineageExtractor()
    return extractor.extract(source_code, file_path)


# =============================================================================
# Main (for testing)
# =============================================================================

if __name__ == "__main__":
    import json

    test_code = '''
"""Example PySpark job with various column patterns."""
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.functions import col, sum, avg, concat

spark = SparkSession.builder.appName("Test").getOrCreate()

# SQL extraction
df1 = spark.sql("""
    SELECT 
        user_id,
        event_type,
        SUM(amount) as total_amount
    FROM staging.events
    WHERE status = 'active'
    GROUP BY user_id, event_type
""")

# DataFrame method chain
df2 = spark.read.parquet("s3://data/events/")
df2 = df2.filter(col("status") == "active")
df2 = df2.select("user_id", "event_type", "amount")

# WithColumn transformation
df3 = df2.withColumn("full_name", concat(col("first_name"), col("last_name")))
df3 = df3.withColumn("event_date", F.to_date(col("event_timestamp")))

# GroupBy and aggregation
summary = df3.groupBy("category", "region") \\
    .agg(
        sum("amount").alias("total_amount"),
        avg("quantity").alias("avg_quantity")
    )

# Variable-based columns
grouping_fields = ["category", "date"]
agg_fields = ["amount", "count"]

dynamic_df = df3.select(grouping_fields)
dynamic_df = df3.groupBy(*grouping_fields).sum("amount")

# Join
joined = df2.join(df3, ["user_id", "event_id"], "inner")

# Write
summary.write.saveAsTable("warehouse.daily_summary")
'''

    result = extract_column_lineage(test_code, "test_job.py")
    print(json.dumps(result.to_dict(), indent=2))
