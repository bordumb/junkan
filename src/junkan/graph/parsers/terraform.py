import json
from typing import Dict, Any, List

class TerraformParser:
    """Parses Terraform Plan JSON (Schema v1)."""
    def __init__(self, plan_json_content: str):
        try:
            self.data = json.loads(plan_json_content)
        except json.JSONDecodeError:
            self.data = {}

    def parse(self) -> List[Dict[str, Any]]:
        relationships = []
        config = self.data.get("configuration", {})
        root_module = config.get("root_module", {})
        resources = root_module.get("resources", [])

        for res in resources:
            addr = res.get("address")
            
            # Explicit depends_on
            for dep in res.get("depends_on", []):
                relationships.append({
                    "upstream": dep,
                    "downstream": addr,
                    "type": "configures"
                })

            # Implicit references
            expressions = res.get("expressions", {})
            for attr, expr in expressions.items():
                for ref in expr.get("references", []):
                    if ref != addr and "var." not in ref:
                        relationships.append({
                            "upstream": ref,
                            "downstream": addr,
                            "type": "configures"
                        })
        return relationships
