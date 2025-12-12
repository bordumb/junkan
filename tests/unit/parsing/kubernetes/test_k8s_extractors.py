"""
Unit tests for Kubernetes Extractors.
"""

from pathlib import Path
import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.kubernetes.extractors.services import ServiceExtractor
from jnkn.parsing.kubernetes.extractors.ingress import IngressExtractor

@pytest.fixture
def make_context():
    def _make(text: str):
        return ExtractionContext(
            file_path=Path("manifest.yaml"),
            file_id="file://manifest.yaml",
            text=text
        )
    return _make

class TestServiceExtractor:
    def test_extract_service(self, make_context):
        text = """
        apiVersion: v1
        kind: Service
        metadata:
          name: my-service
          namespace: prod
        spec:
          selector:
            app: my-app
          ports:
            - port: 80
        """
        extractor = ServiceExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        # Service Node
        svc = next(r for r in results if isinstance(r, Node) and r.type == NodeType.INFRA_RESOURCE)
        assert svc.id == "k8s:prod/service/my-service"
        assert svc.metadata["selector"] == {"app": "my-app"}
        
        # Selector Node (Virtual Config Key)
        sel = next(r for r in results if isinstance(r, Node) and r.type == NodeType.CONFIG_KEY)
        assert sel.name == "selector:my-service"
        
        # Edge (Service -> Selector)
        edge = next(r for r in results if isinstance(r, Edge) and r.type == RelationshipType.CONFIGURES)
        assert edge.source_id == svc.id
        assert edge.target_id == sel.id

    def test_extract_service_no_selector(self, make_context):
        text = """
        apiVersion: v1
        kind: Service
        metadata:
          name: external-svc
        spec:
          type: ExternalName
        """
        extractor = ServiceExtractor()
        results = list(extractor.extract(make_context(text)))
        
        # Should only have Service Node + File Edge, no selector stuff
        assert len([r for r in results if isinstance(r, Node)]) == 1
        assert len([r for r in results if isinstance(r, Edge)]) == 1

class TestIngressExtractor:
    def test_extract_ingress_v1(self, make_context):
        text = """
        apiVersion: networking.k8s.io/v1
        kind: Ingress
        metadata:
          name: my-ingress
          namespace: prod
        spec:
          rules:
          - host: api.example.com
            http:
              paths:
              - path: /api
                backend:
                  service:
                    name: backend-svc
                    port:
                      number: 80
        """
        extractor = IngressExtractor()
        assert extractor.can_extract(make_context(text))
        
        results = list(extractor.extract(make_context(text)))
        
        # Ingress Node
        ing = next(r for r in results if isinstance(r, Node))
        assert ing.id == "k8s:prod/ingress/my-ingress"
        assert "api.example.com" in ing.metadata["hosts"]
        
        # Edge to Service
        edge = next(r for r in results if isinstance(r, Edge) and r.type == RelationshipType.DEPENDS_ON)
        assert edge.source_id == ing.id
        assert edge.target_id == "k8s:prod/service/backend-svc"
        assert edge.metadata["relation"] == "routes_to"

    def test_extract_ingress_legacy(self, make_context):
        # Test legacy backend format (serviceName)
        text = """
        apiVersion: extensions/v1beta1
        kind: Ingress
        metadata:
          name: old-ingress
        spec:
          rules:
          - http:
              paths:
              - backend:
                  serviceName: legacy-svc
                  servicePort: 80
        """
        extractor = IngressExtractor()
        results = list(extractor.extract(make_context(text)))
        
        edge = next(r for r in results if isinstance(r, Edge) and r.type == RelationshipType.DEPENDS_ON)
        assert edge.target_id == "k8s:default/service/legacy-svc"