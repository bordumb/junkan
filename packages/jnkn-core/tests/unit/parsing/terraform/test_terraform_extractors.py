"""
Unit tests for Terraform Extractors.
"""

from pathlib import Path
from typing import List

import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.terraform.extractors.variables import VariableExtractor
from jnkn.parsing.terraform.extractors.modules import ModuleExtractor
from jnkn.parsing.terraform.extractors.references import ReferenceExtractor

@pytest.fixture
def make_context():
    def _make(text: str):
        return ExtractionContext(
            file_path=Path("main.tf"),
            file_id="file://main.tf",
            text=text
        )
    return _make

class TestVariableExtractor:
    def test_extract_full_variable(self, make_context):
        text = """
        variable "db_port" {
          description = "Database port"
          type        = number
          default     = 5432
        }
        """
        extractor = VariableExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        node = next(r for r in results if isinstance(r, Node))
        assert node.id == "infra:var:db_port"
        assert node.type == NodeType.CONFIG_KEY
        assert node.metadata["default"] == "5432"
        assert node.metadata["description"] == "Database port"
        assert node.metadata["type_hint"] == "number"
        
        edge = next(r for r in results if isinstance(r, Edge))
        assert edge.source_id == "file://main.tf"
        assert edge.target_id == "infra:var:db_port"

    def test_extract_minimal_variable(self, make_context):
        text = 'variable "region" {}'
        extractor = VariableExtractor()
        results = list(extractor.extract(make_context(text)))
        
        node = results[0]
        assert node.id == "infra:var:region"
        assert node.metadata["default"] is None

class TestModuleExtractor:
    def test_extract_module_with_inputs(self, make_context):
        text = """
        module "vpc" {
          source = "./modules/vpc"
          
          cidr_block = var.vpc_cidr
          db_endpoint = aws_db_instance.main.endpoint
        }
        """
        extractor = ModuleExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        # Check Module Node
        mod_node = next(r for r in results if isinstance(r, Node))
        assert mod_node.id == "infra:module:vpc"
        assert mod_node.metadata["source"] == "./modules/vpc"
        
        # Check Dependency Edges
        edges = [r for r in results if isinstance(r, Edge) and r.type == RelationshipType.DEPENDS_ON]
        assert len(edges) == 2
        
        # Check var dependency
        var_edge = next(e for e in edges if "var" in e.target_id)
        assert var_edge.target_id == "infra:var:vpc_cidr"
        assert var_edge.metadata["input"] == "cidr_block"
        
        # Check resource dependency (ModuleExtractor currently uses colons for resources)
        res_edge = next(e for e in edges if "aws_db_instance" in e.target_id)
        assert res_edge.target_id == "infra:aws_db_instance:main"

class TestReferenceExtractor:
    def test_extract_resource_reference(self, make_context):
        # We need a block to contain the reference for the heuristic to work
        text = """
        resource "aws_security_group" "sg" {
          vpc_id = aws_vpc.main.id
        }
        """
        extractor = ReferenceExtractor()
        results = list(extractor.extract(make_context(text)))
        
        assert len(results) == 1
        edge = results[0]
        # ReferenceExtractor uses dot notation for resources
        assert edge.source_id == "infra:aws_security_group.sg"
        assert edge.target_id == "infra:aws_vpc.main"
        assert edge.type == RelationshipType.DEPENDS_ON
        assert edge.metadata["attribute"] == "id"

    def test_extract_var_and_local_refs(self, make_context):
        text = """
        resource "test" "t" {
          name = var.project_name
          tag  = local.common_tags
        }
        """
        extractor = ReferenceExtractor()
        results = list(extractor.extract(make_context(text)))
        
        assert len(results) == 2
        
        var_edge = next(e for e in results if "var" in e.target_id)
        assert var_edge.target_id == "infra:var:project_name"
        
        local_edge = next(e for e in results if "local" in e.target_id)
        # ReferenceExtractor uses dot notation for locals
        assert local_edge.target_id == "infra:local.common_tags"

    def test_find_containing_block_logic(self):
        """Test the heuristic for finding the parent block ID."""
        extractor = ReferenceExtractor()
        text = """
        resource "type" "name" {
            key = val
        }
        """
        # Position of 'val'
        pos = text.find("val")
        block_id = extractor._find_containing_block(text, pos)
        # ReferenceExtractor uses dot notation for resources
        assert block_id == "infra:type.name"
        
        # Test outside block
        assert extractor._find_containing_block(text, len(text)) is None