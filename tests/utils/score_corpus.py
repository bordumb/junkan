#!/usr/bin/env python3
"""
Corpus Scoring Utility for Junkan Parser Evaluation

This module provides tools to measure parser precision and recall against
a ground-truth test corpus. It enables data-driven parser improvement by
quantifying exactly what patterns are detected vs missed.

Usage:
    # Score all parsers against full corpus
    uv run python -m tests.utils.score_corpus
    
    # Score specific parser
    uv run python -m tests.utils.score_corpus --parser python
    
    # Score specific test case
    uv run python -m tests.utils.score_corpus --case python/pydantic_settings
    
    # Verbose output showing each match/miss
    uv run python -m tests.utils.score_corpus --verbose
    
    # Generate detailed report
    uv run python -m tests.utils.score_corpus --report report.json

Corpus Structure:
    tests/corpus/
    ├── python/
    │   ├── basic_os_getenv/
    │   │   ├── input.py          # Source file to parse
    │   │   └── expected.json     # Expected detection results
    │   └── pydantic_settings/
    │       ├── input.py
    │       └── expected.json
    ├── terraform/
    │   ├── basic_resources/
    │   │   ├── input.tf
    │   │   └── expected.json
    │   └── module_composition/
    └── integration/
        └── env_to_rds/
            ├── app.py
            ├── main.tf
            └── expected_links.json

Expected JSON Schema:
    {
        "description": "Test case description",
        "env_vars": [
            {
                "name": "DATABASE_HOST",
                "pattern": "os.getenv",
                "line": 5,
                "has_default": false
            }
        ],
        "resources": [
            {
                "name": "main",
                "type": "aws_db_instance",
                "line": 10
            }
        ],
        "edges": [
            {
                "source": "file://app.py",
                "target": "env:DATABASE_HOST",
                "type": "READS"
            }
        ]
    }
"""

from __future__ import annotations

import json
import sys
import argparse
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Set, Optional, Any, Tuple
from enum import Enum
from datetime import datetime

# ANSI colors for terminal output
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"


class MatchStatus(Enum):
    """Status of an expected item."""
    TRUE_POSITIVE = "TP"      # Expected and found
    FALSE_NEGATIVE = "FN"     # Expected but not found
    FALSE_POSITIVE = "FP"     # Found but not expected


@dataclass
class DetectionResult:
    """Result of comparing a single expected item against actual detections."""
    item_type: str            # "env_var", "resource", "edge", etc.
    expected: Dict[str, Any]  # The expected item from ground truth
    actual: Optional[Dict[str, Any]]  # The matched actual item (if found)
    status: MatchStatus
    notes: str = ""           # Additional context (e.g., why it didn't match)


@dataclass
class CaseResult:
    """Results from scoring a single test case."""
    case_name: str
    case_path: Path
    description: str
    
    # Detailed results
    detections: List[DetectionResult] = field(default_factory=list)
    
    # Aggregate counts
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    
    # Timing
    parse_time_ms: float = 0.0
    
    @property
    def precision(self) -> float:
        """Precision = TP / (TP + FP)"""
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0
    
    @property
    def recall(self) -> float:
        """Recall = TP / (TP + FN)"""
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0
    
    @property
    def f1(self) -> float:
        """F1 = 2 * (precision * recall) / (precision + recall)"""
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    @property
    def passed(self) -> bool:
        """Test passes if recall is 100% (no false negatives)."""
        return self.false_negatives == 0


@dataclass
class ParserScore:
    """Aggregate scores for a parser across all test cases."""
    parser_name: str
    cases: List[CaseResult] = field(default_factory=list)
    
    @property
    def total_tp(self) -> int:
        return sum(c.true_positives for c in self.cases)
    
    @property
    def total_fp(self) -> int:
        return sum(c.false_positives for c in self.cases)
    
    @property
    def total_fn(self) -> int:
        return sum(c.false_negatives for c in self.cases)
    
    @property
    def precision(self) -> float:
        denom = self.total_tp + self.total_fp
        return self.total_tp / denom if denom > 0 else 0.0
    
    @property
    def recall(self) -> float:
        denom = self.total_tp + self.total_fn
        return self.total_tp / denom if denom > 0 else 0.0
    
    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0
    
    @property
    def cases_passed(self) -> int:
        return sum(1 for c in self.cases if c.passed)
    
    @property
    def total_cases(self) -> int:
        return len(self.cases)


@dataclass 
class CorpusReport:
    """Full report across all parsers and cases."""
    timestamp: datetime
    corpus_path: Path
    parser_scores: Dict[str, ParserScore] = field(default_factory=dict)
    integration_results: List[CaseResult] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "corpus_path": str(self.corpus_path),
            "summary": {
                parser: {
                    "precision": score.precision,
                    "recall": score.recall,
                    "f1": score.f1,
                    "cases_passed": score.cases_passed,
                    "total_cases": score.total_cases,
                    "true_positives": score.total_tp,
                    "false_positives": score.total_fp,
                    "false_negatives": score.total_fn,
                }
                for parser, score in self.parser_scores.items()
            },
            "details": {
                parser: [
                    {
                        "case": c.case_name,
                        "passed": c.passed,
                        "precision": c.precision,
                        "recall": c.recall,
                        "f1": c.f1,
                        "tp": c.true_positives,
                        "fp": c.false_positives,
                        "fn": c.false_negatives,
                        "parse_time_ms": c.parse_time_ms,
                        "missed": [
                            d.expected for d in c.detections 
                            if d.status == MatchStatus.FALSE_NEGATIVE
                        ],
                        "unexpected": [
                            d.actual for d in c.detections 
                            if d.status == MatchStatus.FALSE_POSITIVE
                        ],
                    }
                    for c in score.cases
                ]
                for parser, score in self.parser_scores.items()
            },
        }


class CorpusScorer:
    """
    Scores parser accuracy against a ground-truth test corpus.
    
    The scorer:
    1. Discovers test cases in the corpus directory
    2. Runs the appropriate parser on each input file
    3. Compares actual detections against expected results
    4. Calculates precision, recall, and F1 scores
    """
    
    def __init__(
        self,
        corpus_path: Path,
        verbose: bool = False,
    ):
        self.corpus_path = corpus_path
        self.verbose = verbose
        self._parsers: Dict[str, Any] = {}
        self._context = None
    
    def _log(self, msg: str, color: str = "") -> None:
        """Print message if verbose."""
        if self.verbose:
            print(f"{color}{msg}{Colors.RESET}")
    
    def _init_parsers(self) -> None:
        """Lazily initialize parsers."""
        if self._parsers:
            return
        
        try:
            from junkan.parsing.base import ParserContext
            from junkan.parsing.python.parser import PythonParser
            from junkan.parsing.terraform.parser import TerraformParser
            
            self._context = ParserContext(root_dir=Path.cwd())
            
            self._parsers = {
                "python": PythonParser(self._context),
                "terraform": TerraformParser(self._context),
            }
            
            # Try to load optional parsers
            try:
                from junkan.parsing.kubernetes.parser import KubernetesParser
                self._parsers["kubernetes"] = KubernetesParser(self._context)
            except ImportError:
                pass
            
            try:
                from junkan.parsing.javascript.parser import JavaScriptParser
                self._parsers["javascript"] = JavaScriptParser(self._context)
            except ImportError:
                pass
            
            try:
                from junkan.parsing.dbt.manifest_parser import DbtManifestParser
                self._parsers["dbt"] = DbtManifestParser(self._context)
            except ImportError:
                pass
            
            try:
                from junkan.parsing.pyspark.parser import PySparkParser
                self._parsers["pyspark"] = PySparkParser(self._context)
            except ImportError:
                pass
            
            try:
                from junkan.parsing.spark_yaml.parser import SparkYamlParser
                self._parsers["spark_yaml"] = SparkYamlParser(self._context)
            except ImportError:
                pass
                
        except ImportError as e:
            print(f"{Colors.RED}Error importing parsers: {e}{Colors.RESET}")
            print("Make sure you're running from the junkan project root with:")
            print("  uv run python -m tests.utils.score_corpus")
            sys.exit(1)
    
    def discover_cases(self, parser_filter: Optional[str] = None) -> Dict[str, List[Path]]:
        """
        Discover test cases in the corpus directory.
        
        Returns:
            Dict mapping parser name to list of case directories
        """
        cases: Dict[str, List[Path]] = {}
        
        for parser_dir in self.corpus_path.iterdir():
            if not parser_dir.is_dir():
                continue
            
            parser_name = parser_dir.name
            
            # Skip integration tests (handled separately)
            if parser_name == "integration":
                continue
            
            # Apply filter if specified
            if parser_filter and parser_name != parser_filter:
                continue
            
            cases[parser_name] = []
            
            for case_dir in parser_dir.iterdir():
                if not case_dir.is_dir():
                    continue
                
                # Check for required files
                expected_file = case_dir / "expected.json"
                if not expected_file.exists():
                    self._log(f"  Skipping {case_dir.name}: no expected.json", Colors.DIM)
                    continue
                
                # Check for at least one input file
                input_files = list(case_dir.glob("input.*"))
                if not input_files:
                    self._log(f"  Skipping {case_dir.name}: no input file", Colors.DIM)
                    continue
                
                cases[parser_name].append(case_dir)
        
        return cases
    
    def _get_input_file(self, case_dir: Path, parser_name: str) -> Optional[Path]:
        """Find the input file for a test case."""
        # Map parser to expected extensions
        extension_map = {
            "python": [".py", ".pyi"],
            "terraform": [".tf"],
            "kubernetes": [".yaml", ".yml"],
            "javascript": [".js", ".ts", ".jsx", ".tsx"],
            "dbt": [".json"],
            "pyspark": [".py"],
            "spark_yaml": [".yml", ".yaml"],
        }
        
        extensions = extension_map.get(parser_name, [])
        
        # First try explicit input.* files
        for ext in extensions:
            input_file = case_dir / f"input{ext}"
            if input_file.exists():
                return input_file
        
        # Fall back to any file with matching extension
        for ext in extensions:
            files = list(case_dir.glob(f"*{ext}"))
            if files:
                return files[0]
        
        return None
    
    def _run_parser(
        self,
        parser_name: str,
        input_file: Path,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], float]:
        """
        Run a parser on an input file.
        
        Returns:
            Tuple of (nodes, edges, parse_time_ms)
        """
        import time
        
        self._init_parsers()
        
        parser = self._parsers.get(parser_name)
        if not parser:
            return [], [], 0.0
        
        content = input_file.read_bytes()
        
        start = time.perf_counter()
        
        nodes = []
        edges = []
        
        try:
            for item in parser.parse(input_file, content):
                # Convert to dict for comparison
                if hasattr(item, 'model_dump'):
                    item_dict = item.model_dump()
                elif hasattr(item, '__dict__'):
                    item_dict = {k: v for k, v in item.__dict__.items() if not k.startswith('_')}
                else:
                    item_dict = {"value": str(item)}
                
                # Classify as node or edge
                if hasattr(item, 'source_id') or 'source_id' in item_dict:
                    edges.append(item_dict)
                else:
                    nodes.append(item_dict)
        
        except Exception as e:
            self._log(f"    Parser error: {e}", Colors.RED)
        
        elapsed_ms = (time.perf_counter() - start) * 1000
        
        return nodes, edges, elapsed_ms
    
    def _match_env_var(
        self,
        expected: Dict[str, Any],
        actual_nodes: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Find a matching env var node."""
        expected_name = expected.get("name", "")
        
        for node in actual_nodes:
            node_type = str(node.get("type", ""))
            node_name = node.get("name", "")
            
            # Check if it's an env var type
            if "env" not in node_type.lower() and node.get("id", "").startswith("env:") is False:
                continue
            
            # Match by name
            if node_name == expected_name:
                return node
            
            # Also check the ID (env:VAR_NAME)
            if node.get("id") == f"env:{expected_name}":
                return node
        
        return None
    
    def _match_resource(
        self,
        expected: Dict[str, Any],
        actual_nodes: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Find a matching infrastructure resource node."""
        expected_name = expected.get("name", "")
        expected_type = expected.get("type", "")
        
        for node in actual_nodes:
            node_type_enum = str(node.get("type", ""))
            node_name = node.get("name", "")
            
            # Check if it's an infra resource
            if "infra" not in node_type_enum.lower() and "resource" not in node_type_enum.lower():
                continue
            
            # Match by name
            if node_name == expected_name:
                # If expected specifies resource type, check metadata
                if expected_type:
                    metadata = node.get("metadata", {})
                    if metadata.get("resource_type") == expected_type:
                        return node
                    # Also check if type is in the ID
                    if expected_type in node.get("id", ""):
                        return node
                else:
                    return node
        
        return None
    
    def _match_table(
        self,
        expected: Dict[str, Any],
        actual_nodes: List[Dict[str, Any]],
        operation: str = "read",
    ) -> Optional[Dict[str, Any]]:
        """
        Find a matching data asset (table/file) node.
        
        Args:
            expected: Expected table definition with 'name' and optionally 'pattern', 'source_type'
            actual_nodes: List of actual parsed nodes
            operation: 'read' or 'write' - used to filter by edge type if needed
        """
        expected_name = expected.get("name", "")
        expected_pattern = expected.get("pattern", "")
        expected_source_type = expected.get("source_type", "")
        
        for node in actual_nodes:
            node_type = str(node.get("type", ""))
            node_name = node.get("name", "")
            node_id = node.get("id", "")
            metadata = node.get("metadata", {})
            
            # Check if it's a data asset
            if "data" not in node_type.lower() and not node_id.startswith("data:"):
                continue
            
            # Match by name (exact or normalized)
            if node_name == expected_name:
                return node
            
            # Also check the ID (data:schema.table or data:s3:bucket/path)
            normalized_expected = expected_name.replace("://", ":")
            if node_id == f"data:{expected_name}" or node_id == f"data:{normalized_expected}":
                return node
            
            # Fuzzy match for paths (ignore trailing slashes)
            if node_name.rstrip('/') == expected_name.rstrip('/'):
                return node
        
        return None
    
    def _match_edge(
        self,
        expected: Dict[str, Any],
        actual_edges: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Find a matching edge."""
        expected_source = expected.get("source", "")
        expected_target = expected.get("target", "")
        expected_type = expected.get("type", "")
        
        for edge in actual_edges:
            source = edge.get("source_id", "")
            target = edge.get("target_id", "")
            edge_type = str(edge.get("type", ""))
            
            # Flexible matching - allow partial matches
            source_match = expected_source in source or source in expected_source
            target_match = expected_target in target or target in expected_target
            type_match = not expected_type or expected_type.lower() in edge_type.lower()
            
            if source_match and target_match and type_match:
                return edge
        
        return None
    
    def score_case(self, case_dir: Path, parser_name: str) -> CaseResult:
        """Score a single test case."""
        case_name = f"{parser_name}/{case_dir.name}"
        
        # Load expected results
        expected_file = case_dir / "expected.json"
        with open(expected_file) as f:
            expected = json.load(f)
        
        description = expected.get("description", "")
        
        result = CaseResult(
            case_name=case_name,
            case_path=case_dir,
            description=description,
        )
        
        # Find input file
        input_file = self._get_input_file(case_dir, parser_name)
        if not input_file:
            self._log(f"  No input file found for {case_name}", Colors.RED)
            return result
        
        # Run parser
        actual_nodes, actual_edges, parse_time = self._run_parser(parser_name, input_file)
        result.parse_time_ms = parse_time
        
        self._log(f"  Parsed {len(actual_nodes)} nodes, {len(actual_edges)} edges in {parse_time:.1f}ms", Colors.DIM)
        
        # Track which actual items have been matched (to find FPs)
        matched_node_indices: Set[int] = set()
        matched_edge_indices: Set[int] = set()
        
        # Score env vars
        for exp_env in expected.get("env_vars", []):
            match = self._match_env_var(exp_env, actual_nodes)
            
            if match:
                idx = actual_nodes.index(match)
                matched_node_indices.add(idx)
                result.detections.append(DetectionResult(
                    item_type="env_var",
                    expected=exp_env,
                    actual=match,
                    status=MatchStatus.TRUE_POSITIVE,
                ))
                result.true_positives += 1
                self._log(f"    ✓ env:{exp_env['name']}", Colors.GREEN)
            else:
                result.detections.append(DetectionResult(
                    item_type="env_var",
                    expected=exp_env,
                    actual=None,
                    status=MatchStatus.FALSE_NEGATIVE,
                    notes=f"Pattern: {exp_env.get('pattern', 'unknown')}",
                ))
                result.false_negatives += 1
                self._log(f"    ✗ env:{exp_env['name']} (MISSED)", Colors.RED)
        
        # Score resources
        for exp_res in expected.get("resources", []):
            match = self._match_resource(exp_res, actual_nodes)
            
            if match:
                idx = actual_nodes.index(match)
                matched_node_indices.add(idx)
                result.detections.append(DetectionResult(
                    item_type="resource",
                    expected=exp_res,
                    actual=match,
                    status=MatchStatus.TRUE_POSITIVE,
                ))
                result.true_positives += 1
                self._log(f"    ✓ resource:{exp_res['name']}", Colors.GREEN)
            else:
                result.detections.append(DetectionResult(
                    item_type="resource",
                    expected=exp_res,
                    actual=None,
                    status=MatchStatus.FALSE_NEGATIVE,
                    notes=f"Type: {exp_res.get('type', 'unknown')}",
                ))
                result.false_negatives += 1
                self._log(f"    ✗ resource:{exp_res['name']} (MISSED)", Colors.RED)
        
        # Score tables_read (PySpark data lineage)
        for exp_table in expected.get("tables_read", []):
            match = self._match_table(exp_table, actual_nodes, operation="read")
            
            if match:
                idx = actual_nodes.index(match)
                matched_node_indices.add(idx)
                result.detections.append(DetectionResult(
                    item_type="table_read",
                    expected=exp_table,
                    actual=match,
                    status=MatchStatus.TRUE_POSITIVE,
                ))
                result.true_positives += 1
                self._log(f"    ✓ read:{exp_table['name']}", Colors.GREEN)
            else:
                result.detections.append(DetectionResult(
                    item_type="table_read",
                    expected=exp_table,
                    actual=None,
                    status=MatchStatus.FALSE_NEGATIVE,
                    notes=f"Pattern: {exp_table.get('pattern', 'unknown')}",
                ))
                result.false_negatives += 1
                self._log(f"    ✗ read:{exp_table['name']} (MISSED)", Colors.RED)
        
        # Score tables_written (PySpark data lineage)
        for exp_table in expected.get("tables_written", []):
            match = self._match_table(exp_table, actual_nodes, operation="write")
            
            if match:
                idx = actual_nodes.index(match)
                matched_node_indices.add(idx)
                result.detections.append(DetectionResult(
                    item_type="table_written",
                    expected=exp_table,
                    actual=match,
                    status=MatchStatus.TRUE_POSITIVE,
                ))
                result.true_positives += 1
                self._log(f"    ✓ write:{exp_table['name']}", Colors.GREEN)
            else:
                result.detections.append(DetectionResult(
                    item_type="table_written",
                    expected=exp_table,
                    actual=None,
                    status=MatchStatus.FALSE_NEGATIVE,
                    notes=f"Pattern: {exp_table.get('pattern', 'unknown')}",
                ))
                result.false_negatives += 1
                self._log(f"    ✗ write:{exp_table['name']} (MISSED)", Colors.RED)
        
        # Score edges
        for exp_edge in expected.get("edges", []):
            match = self._match_edge(exp_edge, actual_edges)
            
            if match:
                idx = actual_edges.index(match)
                matched_edge_indices.add(idx)
                result.detections.append(DetectionResult(
                    item_type="edge",
                    expected=exp_edge,
                    actual=match,
                    status=MatchStatus.TRUE_POSITIVE,
                ))
                result.true_positives += 1
                self._log(f"    ✓ edge:{exp_edge['source']} -> {exp_edge['target']}", Colors.GREEN)
            else:
                result.detections.append(DetectionResult(
                    item_type="edge",
                    expected=exp_edge,
                    actual=None,
                    status=MatchStatus.FALSE_NEGATIVE,
                ))
                result.false_negatives += 1
                self._log(f"    ✗ edge:{exp_edge['source']} -> {exp_edge['target']} (MISSED)", Colors.RED)
        
        # Count false positives (actual items not in expected)
        # Only count env vars, resources, and data assets as FPs - ignore file nodes, imports, etc.
        for i, node in enumerate(actual_nodes):
            if i in matched_node_indices:
                continue
            
            node_type = str(node.get("type", "")).lower()
            node_id = node.get("id", "")
            node_name = node.get("name", "")
            
            # Check if this is explicitly marked as acceptable FP
            acceptable_fps = expected.get("acceptable_false_positives", [])
            if node_name in acceptable_fps:
                continue
            
            # Count env vars as potential false positives
            if "env" in node_type or node_id.startswith("env:"):
                result.detections.append(DetectionResult(
                    item_type="env_var",
                    expected={},
                    actual=node,
                    status=MatchStatus.FALSE_POSITIVE,
                    notes="Detected but not expected",
                ))
                result.false_positives += 1
                self._log(f"    ? env:{node_name} (UNEXPECTED)", Colors.YELLOW)
            
            # Count data assets as potential false positives  
            elif "data" in node_type or node_id.startswith("data:"):
                result.detections.append(DetectionResult(
                    item_type="table",
                    expected={},
                    actual=node,
                    status=MatchStatus.FALSE_POSITIVE,
                    notes="Detected but not expected",
                ))
                result.false_positives += 1
                self._log(f"    ? data:{node_name} (UNEXPECTED)", Colors.YELLOW)
        
        return result
    
    def score_parser(self, parser_name: str, cases: List[Path]) -> ParserScore:
        """Score all cases for a parser."""
        score = ParserScore(parser_name=parser_name)
        
        for case_dir in sorted(cases):
            case_result = self.score_case(case_dir, parser_name)
            score.cases.append(case_result)
        
        return score
    
    def score_all(
        self,
        parser_filter: Optional[str] = None,
        case_filter: Optional[str] = None,
    ) -> CorpusReport:
        """
        Score all parsers against the corpus.
        
        Args:
            parser_filter: Only score this parser
            case_filter: Only score cases matching this pattern
        
        Returns:
            Complete corpus report
        """
        report = CorpusReport(
            timestamp=datetime.now(),
            corpus_path=self.corpus_path,
        )
        
        cases_by_parser = self.discover_cases(parser_filter)
        
        for parser_name, cases in sorted(cases_by_parser.items()):
            if case_filter:
                cases = [c for c in cases if case_filter in str(c)]
            
            if not cases:
                continue
            
            print(f"\n{Colors.BLUE}{Colors.BOLD}Scoring {parser_name} parser ({len(cases)} cases){Colors.RESET}")
            print(f"{Colors.DIM}{'─' * 50}{Colors.RESET}")
            
            score = self.score_parser(parser_name, cases)
            report.parser_scores[parser_name] = score
            
            # Print case results
            for case in score.cases:
                status = f"{Colors.GREEN}PASS{Colors.RESET}" if case.passed else f"{Colors.RED}FAIL{Colors.RESET}"
                print(f"  {status} {case.case_name}")
                
                if self.verbose and not case.passed:
                    for det in case.detections:
                        if det.status == MatchStatus.FALSE_NEGATIVE:
                            print(f"       {Colors.RED}↳ Missed: {det.expected}{Colors.RESET}")
        
        return report
    
    def print_summary(self, report: CorpusReport) -> None:
        """Print a summary of the scoring results."""
        print(f"\n{Colors.BLUE}{'═' * 60}{Colors.RESET}")
        print(f"{Colors.BLUE}{Colors.BOLD}{'CORPUS SCORING SUMMARY':^60}{Colors.RESET}")
        print(f"{Colors.BLUE}{'═' * 60}{Colors.RESET}\n")
        
        for parser_name, score in sorted(report.parser_scores.items()):
            # Color code the F1 score
            f1 = score.f1
            if f1 >= 0.9:
                f1_color = Colors.GREEN
            elif f1 >= 0.7:
                f1_color = Colors.YELLOW
            else:
                f1_color = Colors.RED
            
            print(f"{Colors.BOLD}{parser_name.upper()} PARSER{Colors.RESET}")
            print(f"  Cases:     {score.cases_passed}/{score.total_cases} passed")
            print(f"  Precision: {score.precision:.1%} ({score.total_tp} TP, {score.total_fp} FP)")
            print(f"  Recall:    {score.recall:.1%} ({score.total_tp} TP, {score.total_fn} FN)")
            print(f"  F1 Score:  {f1_color}{f1:.2f}{Colors.RESET}")
            
            # Show worst cases
            failed_cases = [c for c in score.cases if not c.passed]
            if failed_cases and self.verbose:
                print(f"\n  {Colors.DIM}Failing cases:{Colors.RESET}")
                for case in failed_cases[:5]:
                    missed = [d.expected.get('name', str(d.expected)) 
                              for d in case.detections 
                              if d.status == MatchStatus.FALSE_NEGATIVE]
                    print(f"    • {case.case_name}: missed {missed}")
            
            print()
        
        # Overall assessment
        all_recall = sum(s.recall * s.total_cases for s in report.parser_scores.values())
        total_cases = sum(s.total_cases for s in report.parser_scores.values())
        avg_recall = all_recall / total_cases if total_cases > 0 else 0
        
        print(f"{Colors.DIM}{'─' * 60}{Colors.RESET}")
        if avg_recall >= 0.9:
            print(f"{Colors.GREEN}{Colors.BOLD}✅ PRODUCTION READY: Average recall {avg_recall:.1%}{Colors.RESET}")
        elif avg_recall >= 0.7:
            print(f"{Colors.YELLOW}{Colors.BOLD}⚠️  NEEDS WORK: Average recall {avg_recall:.1%}{Colors.RESET}")
        else:
            print(f"{Colors.RED}{Colors.BOLD}❌ NOT READY: Average recall {avg_recall:.1%}{Colors.RESET}")


def main():
    parser = argparse.ArgumentParser(
        description="Score Junkan parsers against a ground-truth test corpus",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          Score all parsers
  %(prog)s --parser python          Score only Python parser
  %(prog)s --case pydantic          Score cases matching 'pydantic'
  %(prog)s --verbose                Show detailed match/miss info
  %(prog)s --report scores.json     Save detailed report to file
        """,
    )
    
    parser.add_argument(
        "--corpus",
        type=Path,
        default=Path("tests/corpus"),
        help="Path to test corpus directory (default: tests/corpus)",
    )
    parser.add_argument(
        "--parser", "-p",
        type=str,
        help="Only score this parser (python, terraform, etc.)",
    )
    parser.add_argument(
        "--case", "-c",
        type=str,
        help="Only score cases matching this pattern",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output for each detection",
    )
    parser.add_argument(
        "--report", "-r",
        type=Path,
        help="Save detailed JSON report to this file",
    )
    
    args = parser.parse_args()
    
    # Validate corpus exists
    if not args.corpus.exists():
        print(f"{Colors.RED}Corpus directory not found: {args.corpus}{Colors.RESET}")
        print(f"\nCreate the corpus structure with:")
        print(f"  mkdir -p {args.corpus}/python/basic_os_getenv")
        print(f"  mkdir -p {args.corpus}/terraform/basic_resources")
        sys.exit(1)
    
    # Run scoring
    scorer = CorpusScorer(args.corpus, verbose=args.verbose)
    report = scorer.score_all(parser_filter=args.parser, case_filter=args.case)
    
    # Print summary
    scorer.print_summary(report)
    
    # Save report if requested
    if args.report:
        with open(args.report, "w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        print(f"\n{Colors.DIM}Report saved to: {args.report}{Colors.RESET}")
    
    # Exit code based on results
    total_fn = sum(s.total_fn for s in report.parser_scores.values())
    sys.exit(0 if total_fn == 0 else 1)


if __name__ == "__main__":
    main()
