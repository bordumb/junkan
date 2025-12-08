import click
import json
import os
from pathlib import Path
from junkan.graph.store import GraphStore
from junkan.models import ImpactRelationship, RelationshipType
from junkan.graph.parsers.terraform import TerraformParser
from junkan.graph.parsers.dbt import DbtParser
from junkan.graph.parsers.universal import UniversalParser

@click.group()
def main():
    """Junkan V2: CI/CD Gatekeeper."""
    pass

@main.command()
@click.option("--tf-plan", type=click.Path(exists=True), help="Path to tfplan.json")
@click.option("--dbt-manifest", type=click.Path(exists=True), help="Path to manifest.json")
@click.option("--code-dir", type=click.Path(exists=True), help="Directory to scan for code")  # <--- New Option
def ingest(tf_plan, dbt_manifest, code_dir):
    """Ingest artifacts into local SQLite graph."""
    store = GraphStore()
    count = 0

    # 1. Infrastructure (Terraform)
    if tf_plan:
        with open(tf_plan) as f:
            parser = TerraformParser(f.read())
            for rel in parser.parse():
                store.add_relationship(ImpactRelationship(
                    upstream_artifact=rel["upstream"],
                    downstream_artifact=rel["downstream"],
                    relationship_type=RelationshipType.CONFIGURES,
                    source="terraform"
                ))
                count += 1

    # 2. Data (dbt)
    if dbt_manifest:
        with open(dbt_manifest) as f:
            parser = DbtParser(f.read())
            for rel in parser.parse():
                store.add_relationship(ImpactRelationship(
                    upstream_artifact=rel["upstream"],
                    downstream_artifact=rel["downstream"],
                    relationship_type=RelationshipType.TRANSFORMS,
                    source="dbt"
                ))
                count += 1
    
    # 3. Application Code (Universal Parser) <--- New Logic
    if code_dir:
        click.echo(f"Scanning directory: {code_dir}")
        for root, dirs, files in os.walk(code_dir):
            # Skip hidden folders and common noise
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["__pycache__", "node_modules", "venv"]]
            
            for file in files:
                file_path = Path(root) / file
                # Only parse supported extensions
                if file_path.suffix in UniversalParser.EXTENSIONS:
                    try:
                        content = file_path.read_text(errors="ignore")
                        parser = UniversalParser(content, str(file_path))
                        
                        for rel in parser.parse():
                            # Normalize path to be relative to the scan root if possible
                            try:
                                downstream = str(file_path.relative_to(code_dir))
                            except ValueError:
                                downstream = str(file_path)

                            store.add_relationship(ImpactRelationship(
                                upstream_artifact=rel.get("upstream", "unknown"),
                                downstream_artifact=downstream,
                                relationship_type=RelationshipType.DEPENDS_ON,
                                source="code_scan"
                            ))
                            count += 1
                    except Exception as e:
                        pass # Skip files we can't read

    click.echo(json.dumps({"status": "success", "relationships_ingested": count}))

@main.command()
@click.argument("artifacts", nargs=-1)
def blast_radius(artifacts):
    """Calculate downstream impact for a list of artifacts."""
    store = GraphStore()
    result = store.calculate_blast_radius(list(artifacts))
    click.echo(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()