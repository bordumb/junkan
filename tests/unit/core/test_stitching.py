"""Unit tests for the stitching module."""

from unittest.mock import MagicMock
import pytest
from jnkn.core.stitching import (
    MatchConfig,
    TokenMatcher,
    EnvVarToInfraRule,
    InfraToInfraRule,
    Stitcher
)
from jnkn.core.types import Node, NodeType, Edge

class TestTokenMatcher:
    def test_normalize(self):
        assert TokenMatcher.normalize("DB_HOST") == "dbhost"
        assert TokenMatcher.normalize("api.url") == "apiurl"

    def test_tokenize(self):
        assert TokenMatcher.tokenize("DB_HOST") == ["db", "host"]
        assert TokenMatcher.tokenize("api.v1.url") == ["api", "v1", "url"]

    def test_significant_overlap(self):
        t1 = ["a", "very", "long", "token"]
        t2 = ["a", "very", "short", "token"]
        # 'a' is length 1, ignored. 'very', 'token' match.
        overlap, score = TokenMatcher.significant_token_overlap(t1, t2, min_length=2)
        assert set(overlap) == {"very", "token"}
        assert score > 0

class TestEnvVarToInfraRule:
    @pytest.fixture
    def graph(self):
        g = MagicMock()
        g.get_node = MagicMock(return_value=None)
        return g

    def test_apply_creates_infra_to_env_edge(self, graph):
        # Setup
        env_node = Node(id="env:DB_HOST", name="DB_HOST", type=NodeType.ENV_VAR)
        infra_node = Node(id="infra:db_host", name="db_host", type=NodeType.INFRA_RESOURCE)
        
        graph.get_nodes_by_type.side_effect = lambda t: {
            NodeType.ENV_VAR: [env_node],
            NodeType.INFRA_RESOURCE: [infra_node]
        }.get(t, [])
        graph.get_node.return_value = infra_node # For validation lookup

        rule = EnvVarToInfraRule()
        edges = rule.apply(graph)

        assert len(edges) == 1
        edge = edges[0]
        # Verify Direction: Infra -> Env
        assert edge.source_id == "infra:db_host"
        assert edge.target_id == "env:DB_HOST"

class TestInfraToInfraRule:
    def test_hierarchy_direction(self):
        rule = InfraToInfraRule()
        vpc = Node(id="infra:vpc", name="main-vpc", type=NodeType.INFRA_RESOURCE)
        subnet = Node(id="infra:subnet", name="main-subnet", type=NodeType.INFRA_RESOURCE)
        
        src, tgt = rule._determine_direction(vpc, subnet)
        assert src == vpc  # VPC is higher level than subnet