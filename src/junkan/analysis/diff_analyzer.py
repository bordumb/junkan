"""
Diff-Aware Analysis Engine.

Compares code between two git refs to identify what actually changed,
rather than just which files changed.

Key Insight:
    "File X was modified" is less useful than
    "Column 'user_id' was removed from the SELECT in file X"

This module:
    1. Gets changed files between two git refs
    2. Parses BOTH versions (base and head) of each file
    3. Diffs the extracted artifacts (columns, tables, jobs)
    4. Reports semantic changes: added, removed, modified

Usage:
    from diff_analyzer import DiffAnalyzer
    
    analyzer = DiffAnalyzer(repo_path="/path/to/repo")
    report = analyzer.analyze("main", "HEAD")
    
    for change in report.column_changes:
        print(f"{change.change_type}: {change.column}")
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple, Union

# Import column lineage extractor
try:
    from junkan.parsing.pyspark.column_lineage import (
        extract_column_lineage,
        ColumnLineageResult,
        ColumnRef,
    )
except ImportError:
    # For standalone usage
    from column_lineage import extract_column_lineage, ColumnLineageResult, ColumnRef


# =============================================================================
# Data Models
# =============================================================================

class ChangeType(Enum):
    """Type of change detected."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    RENAMED = "renamed"
    UNCHANGED = "unchanged"


class ArtifactType(Enum):
    """Type of artifact that changed."""
    FILE = "file"
    TABLE_READ = "table_read"
    TABLE_WRITE = "table_write"
    COLUMN_READ = "column_read"
    COLUMN_WRITE = "column_write"
    COLUMN_TRANSFORM = "column_transform"
    LINEAGE_MAPPING = "lineage_mapping"
    VARIABLE = "variable"


@dataclass
class FileChange:
    """A file that changed between refs."""
    path: str
    change_type: ChangeType
    old_path: Optional[str] = None  # For renames
    additions: int = 0
    deletions: int = 0


@dataclass
class ColumnChange:
    """A column-level change."""
    column: str
    table: Optional[str]
    change_type: ChangeType
    context: str  # select, filter, groupby, etc.
    file_path: str
    line_number_old: Optional[int] = None
    line_number_new: Optional[int] = None
    old_value: Optional[str] = None  # For modifications
    new_value: Optional[str] = None
    
    def __str__(self) -> str:
        table_str = f"{self.table}." if self.table else ""
        return f"{self.change_type.value.upper()}: {table_str}{self.column} ({self.context})"


@dataclass
class TableChange:
    """A table-level change."""
    table: str
    change_type: ChangeType
    direction: str  # read or write
    file_path: str
    
    def __str__(self) -> str:
        return f"{self.change_type.value.upper()}: {self.direction} {self.table}"


@dataclass
class LineageChange:
    """A lineage mapping change."""
    output_column: str
    change_type: ChangeType
    old_sources: List[str] = field(default_factory=list)
    new_sources: List[str] = field(default_factory=list)
    file_path: str = ""
    
    def __str__(self) -> str:
        if self.change_type == ChangeType.ADDED:
            return f"ADDED: {self.output_column} <- {self.new_sources}"
        elif self.change_type == ChangeType.REMOVED:
            return f"REMOVED: {self.output_column} <- {self.old_sources}"
        else:
            return f"MODIFIED: {self.output_column} ({self.old_sources} -> {self.new_sources})"


@dataclass
class TransformChange:
    """A transformation change on a column."""
    column: str
    change_type: ChangeType
    old_transform: Optional[str] = None
    new_transform: Optional[str] = None
    file_path: str = ""
    
    def __str__(self) -> str:
        if self.change_type == ChangeType.MODIFIED:
            return f"TRANSFORM CHANGED: {self.column} ({self.old_transform} -> {self.new_transform})"
        return f"{self.change_type.value.upper()} TRANSFORM: {self.column} ({self.new_transform or self.old_transform})"


@dataclass
class DiffReport:
    """Complete diff analysis report."""
    base_ref: str
    head_ref: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    # File-level changes
    file_changes: List[FileChange] = field(default_factory=list)
    
    # Semantic changes
    column_changes: List[ColumnChange] = field(default_factory=list)
    table_changes: List[TableChange] = field(default_factory=list)
    lineage_changes: List[LineageChange] = field(default_factory=list)
    transform_changes: List[TransformChange] = field(default_factory=list)
    
    # Dynamic references that appeared/disappeared
    dynamic_refs_added: List[str] = field(default_factory=list)
    dynamic_refs_removed: List[str] = field(default_factory=list)
    
    @property
    def has_breaking_changes(self) -> bool:
        """Check if there are potentially breaking changes."""
        # Removed columns or tables are breaking
        removed_columns = [c for c in self.column_changes if c.change_type == ChangeType.REMOVED]
        removed_tables = [t for t in self.table_changes if t.change_type == ChangeType.REMOVED]
        removed_lineage = [l for l in self.lineage_changes if l.change_type == ChangeType.REMOVED]
        
        return bool(removed_columns or removed_tables or removed_lineage)
    
    @property
    def summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            "files_changed": len(self.file_changes),
            "files_added": len([f for f in self.file_changes if f.change_type == ChangeType.ADDED]),
            "files_removed": len([f for f in self.file_changes if f.change_type == ChangeType.REMOVED]),
            "files_modified": len([f for f in self.file_changes if f.change_type == ChangeType.MODIFIED]),
            "columns_added": len([c for c in self.column_changes if c.change_type == ChangeType.ADDED]),
            "columns_removed": len([c for c in self.column_changes if c.change_type == ChangeType.REMOVED]),
            "columns_modified": len([c for c in self.column_changes if c.change_type == ChangeType.MODIFIED]),
            "tables_added": len([t for t in self.table_changes if t.change_type == ChangeType.ADDED]),
            "tables_removed": len([t for t in self.table_changes if t.change_type == ChangeType.REMOVED]),
            "lineage_mappings_changed": len(self.lineage_changes),
            "transforms_changed": len(self.transform_changes),
            "has_breaking_changes": self.has_breaking_changes,
        }
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "timestamp": self.timestamp,
            "summary": self.summary,
            "file_changes": [
                {"path": f.path, "type": f.change_type.value, "additions": f.additions, "deletions": f.deletions}
                for f in self.file_changes
            ],
            "column_changes": [
                {
                    "column": c.column,
                    "table": c.table,
                    "type": c.change_type.value,
                    "context": c.context,
                    "file": c.file_path,
                }
                for c in self.column_changes
            ],
            "table_changes": [
                {"table": t.table, "type": t.change_type.value, "direction": t.direction, "file": t.file_path}
                for t in self.table_changes
            ],
            "lineage_changes": [
                {
                    "output": l.output_column,
                    "type": l.change_type.value,
                    "old_sources": l.old_sources,
                    "new_sources": l.new_sources,
                }
                for l in self.lineage_changes
            ],
            "transform_changes": [
                {
                    "column": t.column,
                    "type": t.change_type.value,
                    "old_transform": t.old_transform,
                    "new_transform": t.new_transform,
                }
                for t in self.transform_changes
            ],
        }
    
    def to_markdown(self) -> str:
        """Generate markdown report."""
        lines = [
            "## 📊 Diff Analysis Report",
            "",
            f"**Base:** `{self.base_ref}` → **Head:** `{self.head_ref}`",
            "",
        ]
        
        # Summary table
        s = self.summary
        lines.extend([
            "### Summary",
            "",
            "| Metric | Count |",
            "|--------|-------|",
            f"| Files Changed | {s['files_changed']} |",
            f"| Columns Added | {s['columns_added']} |",
            f"| Columns Removed | {s['columns_removed']} |",
            f"| Tables Changed | {s['tables_added'] + s['tables_removed']} |",
            f"| Lineage Mappings Changed | {s['lineage_mappings_changed']} |",
            "",
        ])
        
        # Breaking changes warning
        if self.has_breaking_changes:
            lines.extend([
                "### ⚠️ Breaking Changes Detected",
                "",
            ])
            
            removed_cols = [c for c in self.column_changes if c.change_type == ChangeType.REMOVED]
            if removed_cols:
                lines.append("**Removed Columns:**")
                for c in removed_cols:
                    table = f"`{c.table}`." if c.table else ""
                    lines.append(f"- {table}`{c.column}` ({c.context}) in `{c.file_path}`")
                lines.append("")
            
            removed_tables = [t for t in self.table_changes if t.change_type == ChangeType.REMOVED]
            if removed_tables:
                lines.append("**Removed Table References:**")
                for t in removed_tables:
                    lines.append(f"- `{t.table}` ({t.direction}) in `{t.file_path}`")
                lines.append("")
        
        # Column changes
        if self.column_changes:
            lines.extend([
                "### Column Changes",
                "",
            ])
            
            added = [c for c in self.column_changes if c.change_type == ChangeType.ADDED]
            removed = [c for c in self.column_changes if c.change_type == ChangeType.REMOVED]
            modified = [c for c in self.column_changes if c.change_type == ChangeType.MODIFIED]
            
            if added:
                lines.append("**Added:**")
                for c in added:
                    lines.append(f"- ➕ `{c.column}` ({c.context})")
                lines.append("")
            
            if removed:
                lines.append("**Removed:**")
                for c in removed:
                    lines.append(f"- 🗑️ `{c.column}` ({c.context})")
                lines.append("")
            
            if modified:
                lines.append("**Modified:**")
                for c in modified:
                    lines.append(f"- ✏️ `{c.column}` ({c.context})")
                lines.append("")
        
        # Lineage changes
        if self.lineage_changes:
            lines.extend([
                "### Lineage Changes",
                "",
            ])
            for lc in self.lineage_changes:
                if lc.change_type == ChangeType.ADDED:
                    lines.append(f"- ➕ `{lc.output_column}` ← {lc.new_sources}")
                elif lc.change_type == ChangeType.REMOVED:
                    lines.append(f"- 🗑️ `{lc.output_column}` ← {lc.old_sources}")
                else:
                    lines.append(f"- ✏️ `{lc.output_column}`: {lc.old_sources} → {lc.new_sources}")
            lines.append("")
        
        # Transform changes
        if self.transform_changes:
            lines.extend([
                "### Transform Changes",
                "",
            ])
            for tc in self.transform_changes:
                if tc.change_type == ChangeType.MODIFIED:
                    lines.append(f"- `{tc.column}`: `{tc.old_transform}` → `{tc.new_transform}`")
                elif tc.change_type == ChangeType.ADDED:
                    lines.append(f"- ➕ `{tc.column}`: `{tc.new_transform}`")
                else:
                    lines.append(f"- 🗑️ `{tc.column}`: `{tc.old_transform}`")
            lines.append("")
        
        return "\n".join(lines)


# =============================================================================
# Diff Analyzer Engine
# =============================================================================

class DiffAnalyzer:
    """
    Analyzes semantic differences between two git refs.
    
    Instead of just reporting "file X changed", this analyzer:
    1. Parses both versions of changed files
    2. Extracts columns, tables, lineage from each
    3. Computes the semantic diff
    
    Example:
        analyzer = DiffAnalyzer("/path/to/repo")
        report = analyzer.analyze("main", "feature-branch")
        
        for change in report.column_changes:
            if change.change_type == ChangeType.REMOVED:
                print(f"⚠️ Column removed: {change.column}")
    """
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize the analyzer.
        
        Args:
            repo_path: Path to git repository root
        """
        self.repo_path = Path(repo_path).resolve()
        
        # File patterns to analyze
        self.patterns = {
            ".py": self._analyze_python_file,
        }
    
    def analyze(self, base_ref: str = "main", head_ref: str = "HEAD") -> DiffReport:
        """
        Analyze differences between two git refs.
        
        Args:
            base_ref: Base git ref (e.g., "main", "origin/main", commit SHA)
            head_ref: Head git ref (e.g., "HEAD", branch name, commit SHA)
            
        Returns:
            DiffReport with all detected changes
        """
        report = DiffReport(base_ref=base_ref, head_ref=head_ref)
        
        # Step 1: Get list of changed files
        file_changes = self._get_changed_files(base_ref, head_ref)
        report.file_changes = file_changes
        
        # Step 2: For each changed file, analyze both versions
        for fc in file_changes:
            if not self._should_analyze(fc.path):
                continue
            
            # Get file contents at both refs
            base_content = self._get_file_at_ref(fc.path if fc.change_type != ChangeType.RENAMED else fc.old_path, base_ref)
            head_content = self._get_file_at_ref(fc.path, head_ref)
            
            # Analyze the diff
            changes = self._analyze_file_diff(
                fc.path,
                base_content,
                head_content,
                fc.change_type,
            )
            
            # Merge changes into report
            report.column_changes.extend(changes.get("columns", []))
            report.table_changes.extend(changes.get("tables", []))
            report.lineage_changes.extend(changes.get("lineage", []))
            report.transform_changes.extend(changes.get("transforms", []))
            report.dynamic_refs_added.extend(changes.get("dynamic_added", []))
            report.dynamic_refs_removed.extend(changes.get("dynamic_removed", []))
        
        return report
    
    def _get_changed_files(self, base_ref: str, head_ref: str) -> List[FileChange]:
        """Get list of files changed between refs."""
        try:
            # Get file status
            result = subprocess.run(
                ["git", "diff", "--name-status", "--numstat", base_ref, head_ref],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"git diff failed: {e.stderr}")
        
        # Parse name-status output
        status_result = subprocess.run(
            ["git", "diff", "--name-status", base_ref, head_ref],
            capture_output=True,
            text=True,
            cwd=self.repo_path,
        )
        
        # Parse numstat for additions/deletions
        numstat_result = subprocess.run(
            ["git", "diff", "--numstat", base_ref, head_ref],
            capture_output=True,
            text=True,
            cwd=self.repo_path,
        )
        
        # Build file list
        files = []
        status_lines = status_result.stdout.strip().split("\n") if status_result.stdout.strip() else []
        numstat_lines = numstat_result.stdout.strip().split("\n") if numstat_result.stdout.strip() else []
        
        # Parse numstat into a dict
        numstat_dict = {}
        for line in numstat_lines:
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                adds = int(parts[0]) if parts[0] != "-" else 0
                dels = int(parts[1]) if parts[1] != "-" else 0
                path = parts[2]
                numstat_dict[path] = (adds, dels)
        
        for line in status_lines:
            if not line:
                continue
            
            parts = line.split("\t")
            status = parts[0]
            
            if status.startswith("R"):  # Rename
                old_path, new_path = parts[1], parts[2]
                adds, dels = numstat_dict.get(new_path, (0, 0))
                files.append(FileChange(
                    path=new_path,
                    change_type=ChangeType.RENAMED,
                    old_path=old_path,
                    additions=adds,
                    deletions=dels,
                ))
            else:
                path = parts[1]
                change_type = {
                    "A": ChangeType.ADDED,
                    "D": ChangeType.REMOVED,
                    "M": ChangeType.MODIFIED,
                }.get(status[0], ChangeType.MODIFIED)
                
                adds, dels = numstat_dict.get(path, (0, 0))
                files.append(FileChange(
                    path=path,
                    change_type=change_type,
                    additions=adds,
                    deletions=dels,
                ))
        
        return files
    
    def _get_file_at_ref(self, path: str, ref: str) -> Optional[str]:
        """Get file contents at a specific git ref."""
        try:
            result = subprocess.run(
                ["git", "show", f"{ref}:{path}"],
                capture_output=True,
                text=True,
                cwd=self.repo_path,
            )
            if result.returncode == 0:
                return result.stdout
            return None
        except Exception:
            return None
    
    def _should_analyze(self, path: str) -> bool:
        """Check if file should be analyzed."""
        ext = Path(path).suffix
        return ext in self.patterns
    
    def _analyze_file_diff(
        self,
        path: str,
        base_content: Optional[str],
        head_content: Optional[str],
        change_type: ChangeType,
    ) -> Dict[str, List]:
        """Analyze semantic diff for a single file."""
        
        ext = Path(path).suffix
        analyzer_func = self.patterns.get(ext)
        
        if not analyzer_func:
            return {}
        
        return analyzer_func(path, base_content, head_content, change_type)
    
    def _analyze_python_file(
        self,
        path: str,
        base_content: Optional[str],
        head_content: Optional[str],
        change_type: ChangeType,
    ) -> Dict[str, List]:
        """Analyze a Python file for PySpark/column changes."""
        
        changes: Dict[str, List] = {
            "columns": [],
            "tables": [],
            "lineage": [],
            "transforms": [],
            "dynamic_added": [],
            "dynamic_removed": [],
        }
        
        # Parse base version
        base_result = None
        if base_content:
            try:
                base_result = extract_column_lineage(base_content, path)
            except Exception:
                pass
        
        # Parse head version
        head_result = None
        if head_content:
            try:
                head_result = extract_column_lineage(head_content, path)
            except Exception:
                pass
        
        # Handle file added/removed
        if change_type == ChangeType.ADDED and head_result:
            # All columns in head are "added"
            for col in head_result.columns_read:
                changes["columns"].append(ColumnChange(
                    column=col.column,
                    table=col.table,
                    change_type=ChangeType.ADDED,
                    context=col.context.value,
                    file_path=path,
                    line_number_new=col.line_number,
                ))
            for col in head_result.columns_written:
                changes["columns"].append(ColumnChange(
                    column=col.column,
                    table=col.table,
                    change_type=ChangeType.ADDED,
                    context="write",
                    file_path=path,
                    line_number_new=col.line_number,
                ))
            return changes
        
        if change_type == ChangeType.REMOVED and base_result:
            # All columns in base are "removed"
            for col in base_result.columns_read:
                changes["columns"].append(ColumnChange(
                    column=col.column,
                    table=col.table,
                    change_type=ChangeType.REMOVED,
                    context=col.context.value,
                    file_path=path,
                    line_number_old=col.line_number,
                ))
            for col in base_result.columns_written:
                changes["columns"].append(ColumnChange(
                    column=col.column,
                    table=col.table,
                    change_type=ChangeType.REMOVED,
                    context="write",
                    file_path=path,
                    line_number_old=col.line_number,
                ))
            return changes
        
        # Modified file - compute diff
        if base_result and head_result:
            changes = self._diff_column_lineage(path, base_result, head_result)
        
        return changes
    
    def _diff_column_lineage(
        self,
        path: str,
        base: ColumnLineageResult,
        head: ColumnLineageResult,
    ) -> Dict[str, List]:
        """Compute diff between two ColumnLineageResult objects."""
        
        changes: Dict[str, List] = {
            "columns": [],
            "tables": [],
            "lineage": [],
            "transforms": [],
            "dynamic_added": [],
            "dynamic_removed": [],
        }
        
        # === Column Read Changes ===
        base_cols_read = {(c.column, c.table, c.context.value) for c in base.columns_read}
        head_cols_read = {(c.column, c.table, c.context.value) for c in head.columns_read}
        
        # Added columns
        for col, table, ctx in (head_cols_read - base_cols_read):
            changes["columns"].append(ColumnChange(
                column=col,
                table=table,
                change_type=ChangeType.ADDED,
                context=ctx,
                file_path=path,
            ))
        
        # Removed columns
        for col, table, ctx in (base_cols_read - head_cols_read):
            changes["columns"].append(ColumnChange(
                column=col,
                table=table,
                change_type=ChangeType.REMOVED,
                context=ctx,
                file_path=path,
            ))
        
        # === Column Write Changes ===
        base_cols_write = {(c.column, c.table) for c in base.columns_written}
        head_cols_write = {(c.column, c.table) for c in head.columns_written}
        
        for col, table in (head_cols_write - base_cols_write):
            changes["columns"].append(ColumnChange(
                column=col,
                table=table,
                change_type=ChangeType.ADDED,
                context="write",
                file_path=path,
            ))
        
        for col, table in (base_cols_write - head_cols_write):
            changes["columns"].append(ColumnChange(
                column=col,
                table=table,
                change_type=ChangeType.REMOVED,
                context="write",
                file_path=path,
            ))
        
        # === Transform Changes ===
        base_transforms = {c.column: c.transform for c in base.columns_written if c.transform}
        head_transforms = {c.column: c.transform for c in head.columns_written if c.transform}
        
        all_cols = set(base_transforms.keys()) | set(head_transforms.keys())
        for col in all_cols:
            old_t = base_transforms.get(col)
            new_t = head_transforms.get(col)
            
            if old_t != new_t:
                if old_t and new_t:
                    change_type = ChangeType.MODIFIED
                elif new_t:
                    change_type = ChangeType.ADDED
                else:
                    change_type = ChangeType.REMOVED
                
                changes["transforms"].append(TransformChange(
                    column=col,
                    change_type=change_type,
                    old_transform=old_t,
                    new_transform=new_t,
                    file_path=path,
                ))
        
        # === Lineage Mapping Changes ===
        base_lineage = {m.output_column: [s.column for s in m.source_columns] for m in base.lineage}
        head_lineage = {m.output_column: [s.column for s in m.source_columns] for m in head.lineage}
        
        all_outputs = set(base_lineage.keys()) | set(head_lineage.keys())
        for output_col in all_outputs:
            old_sources = base_lineage.get(output_col, [])
            new_sources = head_lineage.get(output_col, [])
            
            if set(old_sources) != set(new_sources):
                if old_sources and new_sources:
                    change_type = ChangeType.MODIFIED
                elif new_sources:
                    change_type = ChangeType.ADDED
                else:
                    change_type = ChangeType.REMOVED
                
                changes["lineage"].append(LineageChange(
                    output_column=output_col,
                    change_type=change_type,
                    old_sources=old_sources,
                    new_sources=new_sources,
                    file_path=path,
                ))
        
        # === Dynamic Reference Changes ===
        base_dynamic = {d.variable_name or d.pattern for d in base.dynamic_refs}
        head_dynamic = {d.variable_name or d.pattern for d in head.dynamic_refs}
        
        changes["dynamic_added"] = list(head_dynamic - base_dynamic)
        changes["dynamic_removed"] = list(base_dynamic - head_dynamic)
        
        return changes


# =============================================================================
# Standalone Analysis (without git)
# =============================================================================

def diff_code(
    base_code: str,
    head_code: str,
    file_path: str = "analysis.py",
) -> DiffReport:
    """
    Analyze diff between two code strings directly.
    
    Useful for testing or when not using git.
    
    Args:
        base_code: Original code
        head_code: Modified code
        file_path: Virtual file path for reporting
        
    Returns:
        DiffReport with detected changes
    """
    analyzer = DiffAnalyzer()
    
    # Create a mock report
    report = DiffReport(base_ref="base", head_ref="head")
    
    # Analyze the diff
    changes = analyzer._analyze_python_file(
        path=file_path,
        base_content=base_code,
        head_content=head_code,
        change_type=ChangeType.MODIFIED,
    )
    
    report.column_changes = changes.get("columns", [])
    report.table_changes = changes.get("tables", [])
    report.lineage_changes = changes.get("lineage", [])
    report.transform_changes = changes.get("transforms", [])
    report.dynamic_refs_added = changes.get("dynamic_added", [])
    report.dynamic_refs_removed = changes.get("dynamic_removed", [])
    
    report.file_changes = [FileChange(path=file_path, change_type=ChangeType.MODIFIED)]
    
    return report


# =============================================================================
# Main (Demo)
# =============================================================================

if __name__ == "__main__":
    # Demo with inline code
    base_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum

spark = SparkSession.builder.getOrCreate()

# Read data
df = spark.read.table("warehouse.events")

# Process
result = df.filter(col("status") == "active") \\
    .select("user_id", "event_type", "amount", "old_column") \\
    .groupBy("user_id") \\
    .agg(sum("amount").alias("total_amount"))

# Write
result.write.saveAsTable("warehouse.user_summary")
'''

    head_code = '''
from pyspark.sql import SparkSession
from pyspark.sql.functions import col, sum, avg

spark = SparkSession.builder.getOrCreate()

# Read data
df = spark.read.table("warehouse.events")

# Process - modified logic
result = df.filter(col("status") == "active") \\
    .filter(col("region") == "US") \\
    .select("user_id", "event_type", "amount", "new_column") \\
    .groupBy("user_id", "region") \\
    .agg(
        sum("amount").alias("total_amount"),
        avg("amount").alias("avg_amount")
    )

# Write
result.write.saveAsTable("warehouse.user_summary")
'''

    print("=" * 70)
    print("DIFF ANALYZER DEMO")
    print("=" * 70)
    
    report = diff_code(base_code, head_code, "etl_job.py")
    
    print(f"\n📊 Summary:")
    for key, value in report.summary.items():
        print(f"   {key}: {value}")
    
    print(f"\n📋 Column Changes ({len(report.column_changes)}):")
    for change in report.column_changes:
        icon = {"added": "➕", "removed": "🗑️", "modified": "✏️"}.get(change.change_type.value, "?")
        print(f"   {icon} {change}")
    
    print(f"\n🔗 Lineage Changes ({len(report.lineage_changes)}):")
    for change in report.lineage_changes:
        print(f"   {change}")
    
    print(f"\n⚙️ Transform Changes ({len(report.transform_changes)}):")
    for change in report.transform_changes:
        print(f"   {change}")
    
    if report.has_breaking_changes:
        print("\n⚠️  BREAKING CHANGES DETECTED!")
    
    print("\n" + "=" * 70)
    print("MARKDOWN OUTPUT")
    print("=" * 70)
    print(report.to_markdown())