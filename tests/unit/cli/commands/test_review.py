"""
Unit tests for the 'review' interactive command.
"""

from unittest.mock import MagicMock, patch
from click.testing import CliRunner
import pytest

from jnkn.cli.commands.review import review
from jnkn.core.types import Edge, RelationshipType


@pytest.fixture
def mock_graph():
    """Create a mock graph with test edges."""
    graph = MagicMock()
    
    # Create a low confidence edge that SHOULD be reviewed
    edge1 = Edge(
        source_id="env:USER_ID",
        target_id="infra:user_db",
        type=RelationshipType.READS,
        confidence=0.4
    )
    
    # Create a high confidence edge that should be SKIPPED
    edge2 = Edge(
        source_id="env:HIGH_CONF",
        target_id="infra:db",
        type=RelationshipType.READS,
        confidence=0.95
    )
    
    graph.iter_edges.return_value = [edge1, edge2]
    return graph


@patch("jnkn.cli.commands.review.load_graph")
@patch("jnkn.cli.commands.review.SuppressionStore")
@patch("jnkn.cli.commands.review.Prompt.ask")
def test_review_no_matches_found(mock_ask, mock_store_cls, mock_load, mock_graph):
    """Test behavior when no edges meet criteria."""
    # Setup graph with only high confidence edges
    edge = Edge(source_id="a", target_id="b", type="reads", confidence=0.9)
    mock_graph.iter_edges.return_value = [edge]
    mock_load.return_value = mock_graph
    
    # Setup empty suppression store
    mock_store = mock_store_cls.return_value
    mock_store.is_suppressed.return_value.suppressed = False

    runner = CliRunner()
    result = runner.invoke(review)

    assert result.exit_code == 0
    assert "No matches found needing review" in result.output


@patch("jnkn.cli.commands.review.load_graph")
@patch("jnkn.cli.commands.review.SuppressionStore")
@patch("jnkn.cli.commands.review.Prompt.ask")
def test_review_suppress_flow(mock_ask, mock_store_cls, mock_load, mock_graph):
    """Test the full suppression flow: Review -> 'n' -> Choose Pattern -> Save."""
    mock_load.return_value = mock_graph
    mock_store = mock_store_cls.return_value
    mock_store.is_suppressed.return_value.suppressed = False

    # Simulate user inputs:
    # 1. 'n' (Suppress this match)
    # 2. '2' (Choose the 2nd pattern option: "env:USER_* -> ...")
    # 3. 'Too generic' (Reason)
    mock_ask.side_effect = ["n", "2", "Too generic"]

    runner = CliRunner()
    result = runner.invoke(review)

    assert result.exit_code == 0
    
    # Verify the suppression was added
    mock_store.add.assert_called_once()
    args, kwargs = mock_store.add.call_args
    
    # Check that we picked a pattern (not just exact match)
    # Based on suggest_patterns logic for "env:USER_ID", option 2 is likely "env:USER_*"
    assert args[0].startswith("env:") 
    assert kwargs['reason'] == "Too generic"
    
    # Verify save was called
    mock_store.save.assert_called_once()


@patch("jnkn.cli.commands.review.load_graph")
@patch("jnkn.cli.commands.review.SuppressionStore")
@patch("jnkn.cli.commands.review.Prompt.ask")
def test_review_skip_already_suppressed(mock_ask, mock_store_cls, mock_load, mock_graph):
    """Test that edges already matching a suppression are filtered out."""
    mock_load.return_value = mock_graph
    mock_store = mock_store_cls.return_value
    
    # Mock is_suppressed to return True
    mock_store.is_suppressed.return_value.suppressed = True

    runner = CliRunner()
    result = runner.invoke(review)

    assert result.exit_code == 0
    # Should exit early because no matches need review
    assert "No matches found" in result.output
    # Should never prompt the user
    mock_ask.assert_not_called()


@patch("jnkn.cli.commands.review.load_graph")
@patch("jnkn.cli.commands.review.SuppressionStore")
@patch("jnkn.cli.commands.review.Prompt.ask")
def test_review_quit(mock_ask, mock_store_cls, mock_load, mock_graph):
    """Test quitting the loop."""
    mock_load.return_value = mock_graph
    mock_store = mock_store_cls.return_value
    mock_store.is_suppressed.return_value.suppressed = False

    # Simulate 'q' input
    mock_ask.return_value = "q"

    runner = CliRunner()
    result = runner.invoke(review)

    assert result.exit_code == 0
    assert "Review complete" in result.output
    # Should verify we processed 0 items
    assert "Processed 0 items" in result.output