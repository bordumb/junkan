"""Unit tests for the stitching module."""

from unittest.mock import MagicMock
import pytest

# We import the core stitching logic
from jnkn.core.stitching import (
    MatchConfig,
    EnvVarToInfraRule,
    InfraToInfraRule,
    Stitcher
)
# We import the robust token matcher (FFI candidate) for token logic tests
from jnkn.stitching.matchers import TokenMatcher
from jnkn.core.types import Node, NodeType, Edge

class TestTokenMatcher:
    """
    Tests for the TokenMatcher FFI candidate.
    """
    def test_normalize(self):
        matcher = TokenMatcher()
        assert matcher.normalize("DB_HOST") == "dbhost"
        assert matcher.normalize("api.url") == "apiurl"

    def test_tokenize(self):
        matcher = TokenMatcher()
        assert matcher.tokenize("DB_HOST") == ["db", "host"]
        assert matcher.tokenize("api.v1.url") == ["api", "v1", "url"]

    def test_significant_overlap(self):
        """Test the robust overlap calculation logic."""
        matcher = TokenMatcher()
        t1 = ["a", "very", "long", "token"]
        t2 = ["a", "very", "short", "token"]
        
        # 'a' is length 1, ignored by default config (min_token_length=3).
        # 'very', 'token' match.
        overlap, score = matcher.calculate_significant_overlap(t1, t2)
        
        assert set(overlap) == {"very", "token"}
        assert score > 0

class TestEnvVarToInfraRule:
    """
    Tests for the EnvVar -> Infra stitching rule.
    Now verifies the 'plan' phase of the Collect-then-Apply pattern.
    """
    @pytest.fixture
    def graph(self):
        g = MagicMock()
        g.get_node = MagicMock(return_value=None)
        return g

    def test_plan_creates_infra_to_env_edge(self, graph):
        # Setup
        # Use PAYMENT_DB_HOST to avoid common token penalties
        env_node = Node(
            id="env:PAYMENT_DB_HOST", 
            name="PAYMENT_DB_HOST", 
            type=NodeType.ENV_VAR, 
            tokens=["payment", "db", "host"]
        )
        infra_node = Node(
            id="infra:payment_db_host", 
            name="payment_db_host", 
            type=NodeType.INFRA_RESOURCE, 
            tokens=["payment", "db", "host"]
        )
        
        # Mock graph lookups
        graph.get_nodes_by_type.side_effect = lambda t: {
            NodeType.ENV_VAR: [env_node],
            NodeType.INFRA_RESOURCE: [infra_node],
            NodeType.CONFIG_KEY: [] 
        }.get(t, [])
        graph.get_node.return_value = infra_node

        rule = EnvVarToInfraRule()
        
        # Call plan() instead of apply()
        plan = rule.plan(graph)
        edges = plan.edges_to_add

        assert len(edges) == 1
        edge = edges[0]
        
        # Verify Direction: Infra (Provider) -> Env (Consumer)
        assert edge.source_id == "infra:payment_db_host"
        assert edge.target_id == "env:PAYMENT_DB_HOST"
        assert edge.type == "provides"  # RelationshipType.PROVIDES

class TestInfraToInfraRule:
    def test_hierarchy_direction(self):
        rule = InfraToInfraRule()
        vpc = Node(id="infra:vpc", name="main-vpc", type=NodeType.INFRA_RESOURCE)
        subnet = Node(id="infra:subnet", name="main-subnet", type=NodeType.INFRA_RESOURCE)
        
        src, tgt = rule._determine_direction(vpc, subnet)
        assert src == vpc  # VPC is higher level than subnet

class TestStitcher:
    """Tests for the main Stitcher orchestrator."""
    
    def test_stitch_orchestration(self):
        """Verify the two-phase commit (plan -> apply)."""
        graph = MagicMock()
        graph.has_edge.return_value = False # Edges don't exist yet
        
        # Mock rule that returns a plan
        mock_rule = MagicMock()
        mock_edge = Edge(source_id="a", target_id="b", type="reads")
        # Plan returns object with edges_to_add attribute
        mock_plan = MagicMock()
        mock_plan.edges_to_add = [mock_edge]
        mock_plan.merge.return_value = mock_plan # fluent interface
        
        mock_rule.plan.return_value = mock_plan
        mock_rule.get_name.return_value = "MockRule"

        stitcher = Stitcher()
        stitcher.rules = [mock_rule]
        
        # Run stitch
        new_edges = stitcher.stitch(graph)
        
        # Verify rule was planned
        mock_rule.plan.assert_called_once_with(graph)
        
        # Verify graph was mutated
        graph.add_edge.assert_called_once_with(mock_edge)
        assert len(new_edges) == 1