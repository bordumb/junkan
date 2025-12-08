import json
from typing import Dict, Any, List

class DbtParser:
    """Parses dbt manifest.json."""
    def __init__(self, content: str):
        try:
            self.data = json.loads(content)
        except json.JSONDecodeError:
            self.data = {}

    def parse(self) -> List[Dict[str, Any]]:
        relationships = []
        nodes = self.data.get("nodes", {})
        
        for key, node in nodes.items():
            downstream = node.get("name")
            # Upstream refs
            for node_id in node.get("depends_on", {}).get("nodes", []):
                # dbt node IDs are usually 'model.project.name'
                # We try to extract just the name for cleaner matching
                upstream = node_id.split(".")[-1]
                relationships.append({
                    "upstream": upstream,
                    "downstream": downstream,
                    "type": "transforms"
                })
        return relationships
