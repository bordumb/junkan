"""
Standardized Python Parser.
"""

import ast
from pathlib import Path
from typing import List, Optional, Union

from ...core.types import Edge, Node, NodeType, RelationshipType
from ..base import LanguageParser, ParserContext


class PythonParser(LanguageParser):
    @property
    def name(self) -> str:
        return "python"

    @property
    def extensions(self) -> List[str]:
        return [".py"]

    def can_parse(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def parse(self, file_path: Path, content: bytes) -> List[Union[Node, Edge]]:
        results: List[Union[Node, Edge]] = []
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []

        rel_path = self._relativize(file_path)
        file_id = f"file://{rel_path}"
        
        # 1. Create the File Node
        file_node = Node(
            id=file_id,
            name=file_path.name,
            type=NodeType.CODE_FILE,
            path=rel_path,
            metadata={"language": "python"}
        )
        results.append(file_node)

        # 2. Walk the AST to find env vars
        for node in ast.walk(tree):
            env_var_name = self._extract_env_var(node)
            if env_var_name:
                env_id = f"env:{env_var_name}"
                
                # Create the EnvVar node
                env_node = Node(
                    id=env_id,
                    name=env_var_name,
                    type=NodeType.ENV_VAR,
                    tokens=[t.lower() for t in env_var_name.split("_")]
                )
                results.append(env_node)
                
                # Create the Edge (File READS EnvVar)
                edge = Edge(
                    source_id=file_id,
                    target_id=env_id,
                    type=RelationshipType.READS,
                    metadata={"line": getattr(node, "lineno", 0)}
                )
                results.append(edge)

        return results

    def _extract_env_var(self, node: ast.AST) -> str | None:
        """
        Detect `os.getenv('VAR')` or `os.environ['VAR']`.
        """
        # Case: os.getenv("VAR")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if getattr(node.func.value, "id", "") == "os" and node.func.attr == "getenv":
                    if node.args and isinstance(node.args[0], ast.Constant):
                        return node.args[0].value
        
        # Case: os.environ["VAR"]
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Attribute):
                if getattr(node.value.value, "id", "") == "os" and node.value.attr == "environ":
                    if isinstance(node.slice, ast.Constant):
                        return node.slice.value
                        
        return None


def create_python_parser(context: Optional[ParserContext] = None) -> PythonParser:
    """Factory function to create a Python parser."""
    return PythonParser(context)