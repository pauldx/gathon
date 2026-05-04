"""Export tools: graph export, wiki generation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from gathon.store import UnifiedStore


def export_graph(
    store: UnifiedStore,
    output_path: str,
    format: str = "json",
) -> dict[str, Any]:
    """Export graph in various formats."""
    g = store.build_networkx_graph()

    if format == "json":
        import json

        from networkx.readwrite import json_graph
        data = json_graph.node_link_data(g)
        Path(output_path).write_text(json.dumps(data, indent=2))
    elif format == "graphml":
        import networkx as nx
        nx.write_graphml(g, output_path)
    else:
        return {"error": f"Unsupported format: {format}"}

    return {
        "format": format,
        "output": output_path,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
    }


def generate_wiki(
    store: UnifiedStore,
    output_dir: str,
) -> dict[str, Any]:
    """Generate markdown wiki from community structure."""
    try:
        from gathon.code_graph.wiki import generate_wiki as _gw
        return _gw(store, output_dir)
    except ImportError:
        return {"error": "wiki module not available"}
