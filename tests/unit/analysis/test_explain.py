"""
Unit tests for the Match Explanation Generator.
"""

import pytest
from unittest.mock import MagicMock
from jnkn.analysis.explain import (
    ExplanationGenerator,
    MatchExplanation,
    NodeInfo,
    AlternativeMatch,
    create_explanation_generator,
)
from jnkn.core.confidence import ConfidenceResult
from jnkn.core.types import NodeType

class TestExplanationGenerator:

    @pytest.fixture
    def mock_graph(self):
        graph = MagicMock()
        graph.get_node.return_value = None
        graph.get_edge.return_value = None
        graph.get_nodes_by_type.return_value = []
        return graph

    @pytest.fixture
    def generator(self, mock_graph):
        return create_explanation_generator(graph=mock_graph)

    def test_initialization(self):
        gen = create_explanation_generator()
        assert gen.graph is None
        assert gen.min_confidence == 0.5

    def test_infer_type_from_id(self):
        """Test static type inference helper."""
        func = ExplanationGenerator._infer_type_from_id
        assert func("env:VAR") == "env_var"
        assert func("infra:res") == "infra_resource"
        assert func("file://path") == "code_file"
        assert func("entity:func") == "code_entity"
        assert func("data:table") == "data_asset"
        assert func("other:thing") == "unknown"

    def test_extract_name_from_id(self):
        """Test name extraction helper."""
        func = ExplanationGenerator._extract_name_from_id
        assert func("env:VAR") == "VAR"
        assert func("file://path/to/file") == "path/to/file"
        assert func("simple_id") == "simple_id"

    def test_get_node_info_from_graph(self, generator, mock_graph):
        """Test retrieving node info when node exists in graph."""
        mock_node = MagicMock()
        mock_node.id = "env:TEST"
        mock_node.name = "TEST"
        mock_node.type.value = "env_var"
        mock_node.tokens = ["test"]
        mock_node.path = "app.py"
        mock_node.metadata = {"line": 10, "extra": "val"}
        
        mock_graph.get_node.return_value = mock_node

        info = generator._get_node_info("env:TEST")
        assert info.id == "env:TEST"
        assert info.line_number == 10
        assert info.metadata["extra"] == "val"

    def test_get_node_info_inferred(self, generator, mock_graph):
        """Test inferring node info when node is missing from graph."""
        mock_graph.get_node.return_value = None # Node not found
        
        info = generator._get_node_info("env:NEW_VAR")
        assert info.name == "NEW_VAR"
        assert info.type == "env_var"
        assert info.tokens == ["new", "var"]

    def test_explain_basic_flow(self, generator, mock_graph):
        """Test main explain method."""
        # Setup edge existence
        mock_edge = MagicMock()
        mock_edge.metadata = {"rule": "test_rule"}
        mock_graph.get_edge.return_value = mock_edge

        # Mock calculator behavior implicitly by inputs
        # (Calculator logic is tested in test_confidence.py)
        
        explanation = generator.explain(
            "env:DB", "infra:db", find_alternatives=False
        )
        
        assert isinstance(explanation, MatchExplanation)
        assert explanation.edge_exists is True
        assert explanation.edge_metadata["rule"] == "test_rule"
        assert explanation.confidence_result.score >= 0.0

    def test_find_alternatives(self, generator, mock_graph):
        """Test logic for finding alternative matches."""
        # Setup source
        source_info = NodeInfo("env:DB", "DB", "env_var", ["db"])
        
        # Setup candidates in graph
        c1 = MagicMock()
        c1.id, c1.name, c1.tokens = "infra:db", "db", ["db"] # Exact match
        
        c2 = MagicMock()
        c2.id, c2.name, c2.tokens = "infra:other", "other", ["other"] # No match
        
        mock_graph.get_nodes_by_type.return_value = [c1, c2]

        # Call internal method
        alts = generator._find_alternatives(source_info, "infra:different_target")
        
        # c1 should be an alternative because it matches tokens
        # c2 should not be because tokens don't match
        assert len(alts) >= 1
        assert alts[0].node_id == "infra:db"
        assert alts[0].score > 0

    def test_find_alternatives_candidate_types(self, generator, mock_graph):
        """Test selection of candidate types based on source."""
        # 1. Source is env
        generator._find_alternatives(NodeInfo("env:x", "x", "env", []), "")
        mock_graph.get_nodes_by_type.assert_called_with(NodeType.INFRA_RESOURCE)
        
        # 2. Source is infra
        generator._find_alternatives(NodeInfo("infra:x", "x", "infra", []), "")
        # Should call for INFRA and ENV
        args_list = mock_graph.get_nodes_by_type.call_args_list
        assert any(NodeType.ENV_VAR in args[0] for args in args_list)

        # 3. Source is code/other
        generator._find_alternatives(NodeInfo("file:x", "x", "file", []), "")
        # Should check data assets too
        args_list = mock_graph.get_nodes_by_type.call_args_list
        assert any(NodeType.DATA_ASSET in args[0] for args in args_list)

    def test_explain_why_not_low_score(self, generator):
        """Test explain_why_not when score is low."""
        # Create generator with high threshold
        gen = create_explanation_generator(min_confidence=0.9)
        
        # Explain a mismatch
        text = gen.explain_why_not("env:A", "infra:B")
        
        assert "below threshold" in text
        assert "No overlapping tokens" in text
        assert "Details:" in text

    def test_explain_why_not_edge_exists(self, generator, mock_graph):
        """Test explain_why_not when edge actually exists."""
        mock_graph.get_edge.return_value = MagicMock() # Edge exists
        
        text = generator.explain_why_not("env:A", "env:A")
        assert "Match DOES exist" in text

    def test_explain_why_not_high_score_missing_edge(self, generator, mock_graph):
        """Test explain_why_not when score is high but edge is missing."""
        mock_graph.get_edge.return_value = None # No edge
        
        text = generator.explain_why_not("env:Exact", "infra:Exact")
        assert "Score" in text
        assert "above threshold, but no edge found" in text

    def test_explain_why_not_penalties(self, generator):
        """Test that penalties are listed in why_not."""
        # Force a penalty (short tokens)
        text = generator.explain_why_not("env:id", "infra:id")
        assert "Penalties applied" in text
        assert "short_token" in text

    def test_format_output(self, generator):
        """Test formatting of the explanation."""
        # Create a dummy explanation
        cr = ConfidenceResult(score=0.85)
        cr.signals = [{'weight': 0.9, 'signal': 'test', 'details': 'd', 'matched_tokens': ['a']}]
        cr.penalties = [{'multiplier': 0.5, 'penalty_type': 'p', 'reason': 'r'}]
        
        expl = MatchExplanation(
            source=NodeInfo("s", "s", "t", [], path="p", line_number=1),
            target=NodeInfo("t", "t", "t", [], path="p", line_number=1),
            confidence_result=cr,
            edge_exists=True,
            edge_metadata={"key": "val"},
            alternatives=[AlternativeMatch("alt", "alt", 0.5, "r", ["t"])]
        )

        output = generator.format(expl)
        
        assert "Source: s" in output
        assert "Found in: p:1" in output
        assert "test: ['a']" in output
        assert "[x0.50] p" in output
        assert "Edge Status: EXISTS" in output
        assert "key: val" in output
        assert "ALTERNATIVE MATCHES" in output

    def test_format_output_edge_status_logic(self, generator):
        """Test edge status messaging in format."""
        cr = ConfidenceResult(score=0.1)
        expl = MatchExplanation(
            source=NodeInfo("s", "s", "t", []),
            target=NodeInfo("t", "t", "t", []),
            confidence_result=cr,
            edge_exists=False
        )
        
        # Case: Below threshold
        output = generator.format(expl)
        assert "Would be REJECTED" in output

        # Case: Above threshold
        expl.confidence_result.score = 0.9
        output = generator.format(expl)
        assert "Would be created" in output

    def test_format_brief(self, generator):
        """Test format_brief."""
        cr = ConfidenceResult(score=0.9)
        expl = MatchExplanation(
            source=NodeInfo("s", "s", "t", []),
            target=NodeInfo("t", "t", "t", []),
            confidence_result=cr,
            edge_exists=True
        )
        brief = generator.format_brief(expl)
        assert "s -> t: 0.90 (HIGH, EXISTS)" in brief

    def test_format_signals_variations(self, generator):
        """Test formatting of signals with different data available."""
        # 1. Signal with no details/tokens
        cr = ConfidenceResult(score=0.5)
        cr.signals = [{'weight': 0.5, 'signal': 'simple'}]
        expl = MatchExplanation(
            source=NodeInfo("s", "s", "t", []),
            target=NodeInfo("t", "t", "t", []),
            confidence_result=cr
        )
        out = generator.format(expl)
        assert "[+0.50] simple" in out

        # 2. Signal with details only
        cr.signals = [{'weight': 0.5, 'signal': 'det', 'details': 'foo'}]
        out = generator.format(expl)
        assert "foo" in out

        # 3. No signals
        cr.signals = []
        out = generator.format(expl)
        assert "(none matched)" in out

    def test_alternatives_filtering(self, generator, mock_graph):
        """Test that the target itself is excluded from alternatives."""
        # If we ask for alternatives to Target A, and Target A is in the graph,
        # it shouldn't show up in the alternatives list.
        target_node = MagicMock()
        target_node.id = "infra:target"
        target_node.name = "target"
        target_node.tokens = ["target"]
        
        mock_graph.get_nodes_by_type.return_value = [target_node]
        
        source_info = NodeInfo("env:target", "target", "env", ["target"])
        
        alts = generator._find_alternatives(source_info, "infra:target")
        assert len(alts) == 0