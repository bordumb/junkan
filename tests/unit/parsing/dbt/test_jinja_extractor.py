"""
Unit tests for the dbt Jinja Extractor.
"""

from pathlib import Path
from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.dbt.extractors.jinja import JinjaExtractor

def test_extract_env_vars():
    text = """
    version: 2
    sources:
      - name: stripe
        database: {{ env_var('STRIPE_DATABASE', 'raw') }}
        schema: {{ env_var('STRIPE_SCHEMA') }}
    """
    ctx = ExtractionContext(
        file_path=Path("models/sources.yml"),
        file_id="file://models/sources.yml",
        text=text
    )
    
    extractor = JinjaExtractor()
    assert extractor.can_extract(ctx)
    
    results = list(extractor.extract(ctx))
    
    # Check Env Var Nodes
    env_nodes = [r for r in results if isinstance(r, Node) and r.type == NodeType.ENV_VAR]
    assert len(env_nodes) == 2
    
    stripe_db = next(n for n in env_nodes if n.name == "STRIPE_DATABASE")
    assert stripe_db.id == "env:STRIPE_DATABASE"
    
    stripe_schema = next(n for n in env_nodes if n.name == "STRIPE_SCHEMA")
    assert stripe_schema.id == "env:STRIPE_SCHEMA"
    
    # Check Edges (File READS Env Var)
    edges = [r for r in results if isinstance(r, Edge)]
    assert len(edges) == 2
    assert edges[0].type == RelationshipType.READS
    assert edges[0].target_id == "env:STRIPE_DATABASE"

def test_extract_dbt_vars():
    text = "select * from {{ source(var('source_name'), 'table') }}"
    ctx = ExtractionContext(
        file_path=Path("models/my_model.sql"),
        file_id="file://models/my_model.sql",
        text=text
    )
    
    extractor = JinjaExtractor()
    results = list(extractor.extract(ctx))
    
    # Check Config Node
    config_nodes = [r for r in results if isinstance(r, Node)]
    assert len(config_nodes) == 1
    assert config_nodes[0].id == "config:dbt:source_name"
    assert config_nodes[0].type == NodeType.CONFIG_KEY
    
    # Check Edge
    edges = [r for r in results if isinstance(r, Edge)]
    assert len(edges) == 1
    assert edges[0].target_id == "config:dbt:source_name"

def test_no_matches():
    text = "select * from raw.table"
    ctx = ExtractionContext(file_path=Path("test.sql"), file_id="f", text=text)
    extractor = JinjaExtractor()
    
    assert not extractor.can_extract(ctx)
    assert list(extractor.extract(ctx)) == []