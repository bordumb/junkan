"""
Trace Command - Find paths between two nodes.
"""

import click
from typing import Optional, Any, List, Set

from ..utils import echo_error, load_graph
from ...core.types import RelationshipType


@click.command()
@click.argument("source")
@click.argument("target")
@click.option("-g", "--graph", "graph_file", default=".jnkn/jnkn.db",
              help="Path to graph JSON file or DB")
@click.option("--max-paths", default=5, help="Maximum paths to show")
def trace(source: str, target: str, graph_file: str, max_paths: int) -> None:
    """
    Trace lineage path between two nodes.
    Shows how data flows from source to target.
    """
    graph = load_graph(graph_file)
    if graph is None:
        return

    # Resolve partial names
    source_id = _resolve_node(graph, source, "source")
    if source_id is None:
        return

    target_id = _resolve_node(graph, target, "target")
    if target_id is None:
        return

    # 1. Semantic Trace (Data Flow)
    paths = _semantic_bfs(graph, source_id, target_id)

    # 2. Fallback: Reverse Dependency Trace
    if not paths:
        rev_paths = graph.trace(target_id, source_id)
        if rev_paths:
            click.echo()
            click.echo(click.style("ℹ️  Found dependency path (Consumer -> Provider).", fg="blue"))
            click.echo(click.style("    Visualizing impact flow (Provider -> Consumer):", fg="blue"))
            # Reverse the list to show Source -> Target visual
            paths = [p[::-1] for p in rev_paths]

    if not paths:
        click.echo()
        click.echo(click.style("No path found", fg="yellow") + " between:")
        click.echo(f"  Source: {source_id}")
        click.echo(f"  Target: {target_id}")
        return

    # Print results
    click.echo()
    click.echo(f"🔗 {click.style('Lineage Trace', bold=True)}")
    click.echo("═" * 60)
    click.echo(f"From: {click.style(source_id, fg='cyan')}")
    click.echo(f"To:   {click.style(target_id, fg='green')}")
    click.echo()
    click.echo(f"{len(paths)} path(s) found:")
    click.echo()

    # Sort by length (shortest first)
    sorted_paths = sorted(paths, key=len)[:max_paths]

    for i, path in enumerate(sorted_paths, 1):
        click.echo(f" Path {i}: ({len(path)} steps)")
        for j, node_id in enumerate(path):
            connector = "└─" if j == len(path) - 1 else "├─"
            node = graph.get_node(node_id)
            name = node.name if node else node_id
            
            # Color code based on type
            color = "white"
            if node_id.startswith("env:"): color = "red"
            elif node_id.startswith("infra:"): color = "magenta"
            elif node_id.startswith("file:"): color = "green"
            elif node_id.startswith("data:"): color = "blue"
            elif node_id.startswith("job:"): color = "yellow"
            
            click.echo(f"    {connector} {click.style(name, fg=color)}")
        click.echo()

    if len(paths) > max_paths:
        click.echo(f"  ... and {len(paths) - max_paths} more paths")


def _resolve_node(graph: Any, name: str, label: str) -> Optional[str]:
    """Resolve partial name to full node ID."""
    if graph.has_node(name):
        return name

    # Specific Heuristic for Terraform Outputs
    if name.startswith("infra:") and "output" not in name:
        candidate = name.replace("infra:", "infra:output:")
        if graph.has_node(candidate):
            return candidate
            
    # Generic Terraform Resource Heuristic
    if name.startswith("infra:") and "." in name:
        candidate = name.replace(".", ":")
        if graph.has_node(candidate):
            return candidate

    matches = graph.find_nodes(name)
    
    if not matches:
        echo_error(f"No node found matching {label}: {name}")
        return None
        
    if len(matches) > 1:
        if name in matches: return name
        if name.isupper():
            env_match = next((m for m in matches if m == f"env:{name}"), None)
            if env_match: return env_match
        if "infra" in name:
             out_match = next((m for m in matches if "output" in m), None)
             if out_match: return out_match
        
        click.echo(f"Ambiguous {label} '{name}'. Using first match: {matches[0]}")
        
    return matches[0]


def _get_all_edges_safe(graph: Any) -> List[Any]:
    """Safely retrieve all edges from the graph."""
    if hasattr(graph, "iter_edges"):
        return list(graph.iter_edges())
    if hasattr(graph, "edges"):
        return graph.edges
    if hasattr(graph, "_graph") and hasattr(graph._graph, "edges"):
        return graph._graph.edges()
    return []


def _semantic_bfs(graph: Any, start: str, end: str) -> List[List[str]]:
    """
    Perform a BFS that follows 'Data Flow' rather than just 'Dependency'.
    Robustly handles String vs Enum types for edges.
    """
    all_edges = _get_all_edges_safe(graph)
    
    queue = [[start]]
    visited = {start}
    found_paths = []
    
    max_depth = 15 
    
    # Define sets using string values for robust comparison
    # Downstream Types: Provider -> Consumer
    FORWARD_TYPES = {
        str(RelationshipType.PROVIDES).lower(),
        str(RelationshipType.WRITES).lower(), 
        str(RelationshipType.FLOWS_TO).lower(),
        str(RelationshipType.PROVISIONS).lower(),
        "provides", "writes", "flows_to", "provisions"
    }
    
    # Upstream Types: Consumer -> Provider
    # These edges point Consumer -> Provider, but Data flows Provider -> Consumer
    REVERSE_TYPES = {
        str(RelationshipType.READS).lower(),
        str(RelationshipType.DEPENDS_ON).lower(),
        "reads", "depends_on"
    }

    while queue:
        path = queue.pop(0)
        current_node = path[-1]
        
        if len(path) > max_depth:
            continue
            
        if current_node == end:
            found_paths.append(path)
            continue
            
        neighbors = set()
        
        for edge in all_edges:
            s = getattr(edge, "source_id", None) or edge.get("source_id")
            t = getattr(edge, "target_id", None) or edge.get("target_id")
            
            # Robust type extraction
            raw_type = getattr(edge, "type", None) or edge.get("type")
            r_type = str(raw_type).lower() if raw_type else ""
            
            # Forward Traversal (Downstream)
            if s == current_node and r_type in FORWARD_TYPES:
                neighbors.add(t)
            
            # Reverse Traversal (Upstream consumers)
            if t == current_node and r_type in REVERSE_TYPES:
                neighbors.add(s)
        
        for neighbor in neighbors:
            if neighbor not in visited and neighbor:
                visited.add(neighbor)
                new_path = list(path)
                new_path.append(neighbor)
                queue.append(new_path)
                    
    return found_paths