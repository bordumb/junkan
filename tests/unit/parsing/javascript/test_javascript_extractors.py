"""
Unit tests for JavaScript/TypeScript Extractors (Next.js & Package.json).
"""

import json
from pathlib import Path
import pytest

from jnkn.core.types import Node, Edge, NodeType, RelationshipType
from jnkn.parsing.base import ExtractionContext
from jnkn.parsing.javascript.extractors.nextjs import NextJSExtractor
from jnkn.parsing.javascript.extractors.package_json import PackageJsonExtractor

class TestNextJSExtractor:
    def test_api_route_detection(self):
        extractor = NextJSExtractor()
        
        # Test file in pages/api
        path = Path("pages/api/users/[id].ts")
        ctx = ExtractionContext(file_path=path, file_id="f", text="")
        
        assert extractor.can_extract(ctx)
        results = list(extractor.extract(ctx))
        
        node = results[0]
        assert node.id == "api:/api/users/[id]"
        assert node.metadata["type"] == "api_route"
        
        # Test file in app/api (Next.js 13+)
        path_app = Path("app/api/auth/route.ts")
        ctx_app = ExtractionContext(file_path=path_app, file_id="f", text="")
        
        results_app = list(extractor.extract(ctx_app))
        node_app = results_app[0]
        # route.ts usually maps to the folder name in App Router
        assert "/api/auth/route" in node_app.name

    def test_server_side_props(self):
        text = """
        export async function getServerSideProps() {
            return { props: {} }
        }
        """
        ctx = ExtractionContext(
            file_path=Path("pages/dashboard.js"), 
            file_id="f", 
            text=text
        )
        extractor = NextJSExtractor()
        results = list(extractor.extract(ctx))
        
        # Should find getServerSideProps entity
        nodes = [r for r in results if isinstance(r, Node)]
        assert len(nodes) == 1
        assert nodes[0].name == "getServerSideProps"
        assert nodes[0].metadata["runs_on"] == "server"

class TestPackageJsonExtractor:
    def test_extract_dependencies(self):
        content = {
            "name": "my-app",
            "dependencies": {
                "react": "^18.0.0",
                "axios": "1.0.0"
            },
            "scripts": {
                "start": "next start",
                "test": "jest"
            }
        }
        text = json.dumps(content)
        ctx = ExtractionContext(
            file_path=Path("package.json"),
            file_id="file://package.json",
            text=text
        )
        
        extractor = PackageJsonExtractor()
        assert extractor.can_extract(ctx)
        
        results = list(extractor.extract(ctx))
        nodes = [r for r in results if isinstance(r, Node)]
        edges = [r for r in results if isinstance(r, Edge)]
        
        # Verify dependencies
        react_node = next(n for n in nodes if n.name == "react")
        assert react_node.type == NodeType.CODE_ENTITY
        assert react_node.metadata["version"] == "^18.0.0"
        
        # Verify scripts (Jobs)
        start_job = next(n for n in nodes if n.name == "start")
        assert start_job.type == NodeType.JOB
        assert start_job.metadata["command"] == "next start"
        
        # Verify edges
        assert len(edges) == 4 # 2 deps + 2 scripts