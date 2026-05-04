"""Unified export: HTML viz, Obsidian, Neo4j, GraphML, SVG, JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import networkx as nx

from gathon.store import UnifiedStore

_FILE_TYPE_COLORS = {
    "code": "#4A90D9",
    "document": "#27AE60",
    "paper": "#8E44AD",
    "image": "#E67E22",
    "video": "#E74C3C",
    "config": "#95A5A6",
    "api_spec": "#F39C12",
}

_EDGE_KIND_COLORS = {
    "CALLS": "#3498DB",
    "IMPORTS_FROM": "#9B59B6",
    "INHERITS": "#E74C3C",
    "CONTAINS": "#95A5A6",
    "REFERENCES": "#F39C12",
    "TESTED_BY": "#27AE60",
    "SEMANTICALLY_SIMILAR": "#1ABC9C",
}


def export_unified(
    store: UnifiedStore,
    output_path: str,
    fmt: str = "json",
) -> dict[str, Any]:
    """Export graph in specified format. Returns summary dict."""
    g = store.build_networkx_graph()

    if fmt == "json":
        return _export_json(g, store, output_path)
    elif fmt == "html":
        return _export_html(g, store, output_path)
    elif fmt == "graphml":
        return _export_graphml(g, output_path)
    elif fmt == "obsidian":
        return _export_obsidian(g, store, output_path)
    elif fmt == "svg":
        return _export_svg(g, output_path)
    else:
        return {"error": f"Unsupported format: {fmt}"}


def _export_json(
    g: nx.DiGraph,
    store: UnifiedStore,
    output_path: str,
) -> dict[str, Any]:
    """Export as enriched JSON with file_type colors."""
    nodes_data = []
    for qn, data in g.nodes(data=True):
        ft = data.get("file_type", "code")
        nodes_data.append({
            "id": qn,
            "label": data.get("name", qn),
            "kind": data.get("kind", ""),
            "file_type": ft,
            "file_path": data.get("file_path", ""),
            "pipeline": data.get("pipeline", ""),
            "color": _FILE_TYPE_COLORS.get(ft, "#999"),
        })

    edges_data = []
    for src, tgt, data in g.edges(data=True):
        kind = data.get("kind", "")
        edges_data.append({
            "source": src,
            "target": tgt,
            "kind": kind,
            "relation": data.get("relation", ""),
            "weight": data.get("weight", 1.0),
            "color": _EDGE_KIND_COLORS.get(kind, "#CCC"),
        })

    output = {
        "nodes": nodes_data,
        "edges": edges_data,
        "meta": {
            "node_count": len(nodes_data),
            "edge_count": len(edges_data),
            "file_type_colors": _FILE_TYPE_COLORS,
        },
    }

    Path(output_path).write_text(json.dumps(output, indent=2))
    return {
        "format": "json",
        "output": output_path,
        "nodes": len(nodes_data),
        "edges": len(edges_data),
    }


def _export_html(
    g: nx.DiGraph,
    store: UnifiedStore,
    output_path: str,
) -> dict[str, Any]:
    """Export as interactive vis.js HTML."""
    if g.number_of_nodes() > 5000:
        return {"error": "Graph too large for HTML export (>5000 nodes)"}

    communities: dict[int, list[str]] = {}
    for qn, data in g.nodes(data=True):
        cid = 0
        ft = data.get("file_type", "code")
        if ft != "code":
            cid = 1
        communities.setdefault(cid, []).append(qn)

    colors = ["#4A90D9", "#27AE60", "#8E44AD", "#E67E22", "#E74C3C",
              "#95A5A6", "#F39C12", "#3498DB", "#1ABC9C", "#C0392B"]

    nodes_data = []
    for qn in g.nodes():
        data = g.nodes[qn]
        cid = next((cid for cid, nodes in communities.items() if qn in nodes), 0)
        degree = g.degree(qn)
        nodes_data.append({
            "id": qn,
            "label": data.get("name", qn),
            "title": f"{data.get('kind', 'Unknown')}\n{qn}",
            "size": 20 + min(50, degree * 3),
            "color": colors[cid % len(colors)],
            "community": cid,
        })

    edges_data = []
    for src, tgt, data in g.edges(data=True):
        confidence = data.get("confidence_tier", "EXTRACTED")
        edges_data.append({
            "from": src,
            "to": tgt,
            "title": f"{data.get('kind', 'UNKNOWN')}: {data.get('relation', '')}",
            "dashes": confidence != "EXTRACTED",
            "width": 2 if confidence == "EXTRACTED" else 1,
        })

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Gathon Knowledge Graph</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/vis/4.21.0/vis.min.css" rel="stylesheet" />
    <style>
        body {{ font-family: sans-serif; margin: 0; padding: 10px; }}
        #network {{ width: 100%; height: 90vh; border: 1px solid #ccc; }}
        #legend {{ position: absolute; top: 10px; left: 10px; background: white; padding: 10px; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
        .legend-item {{ margin: 5px 0; }}
        .legend-color {{ display: inline-block; width: 15px; height: 15px; margin-right: 5px; vertical-align: middle; }}
        #search {{ position: absolute; top: 10px; right: 10px; }}
        input[type="text"] {{ padding: 8px; width: 200px; }}
    </style>
</head>
<body>
    <div id="legend">
        <div style="font-weight: bold; margin-bottom: 10px;">Communities</div>
"""

    for cid in sorted(communities.keys()):
        html += f'<div class="legend-item"><span class="legend-color" style="background: {colors[cid % len(colors)]};"></span>{cid}: {len(communities[cid])} nodes</div>'

    html += f"""
    </div>
    <div id="search">
        <input type="text" id="searchBox" placeholder="Search nodes...">
    </div>
    <div id="network"></div>
    <script type="text/javascript">
        var nodes = new vis.DataSet({json.dumps(nodes_data)});
        var edges = new vis.DataSet({json.dumps(edges_data)});
        var container = document.getElementById('network');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            physics: {{
                enabled: true,
                barnesHut: {{ gravitationalConstant: -26000, centralGravity: 0.3, springLength: 200 }},
                maxVelocity: 50,
                stabilization: {{ iterations: 200 }}
            }},
            interaction: {{ navigationButtons: true, keyboard: true }},
            nodes: {{ physics: true }},
            edges: {{ arrows: 'to', smooth: {{ type: 'continuous' }} }}
        }};
        var network = new vis.Network(container, data, options);

        document.getElementById('searchBox').addEventListener('keyup', function(e) {{
            var query = e.target.value.toLowerCase();
            nodes.forEach(function(node) {{
                var matches = node.label.toLowerCase().includes(query) || node.id.toLowerCase().includes(query);
                nodes.update({{ id: node.id, hidden: !matches && query.length > 0 }});
            }});
            network.fit();
        }});
    </script>
</body>
</html>"""

    Path(output_path).write_text(html, encoding="utf-8")
    return {{
        "format": "html",
        "output": output_path,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
    }}


def _export_graphml(
    g: nx.DiGraph,
    output_path: str,
) -> dict[str, Any]:
    """Export as GraphML."""
    nx.write_graphml(g, output_path)
    return {
        "format": "graphml",
        "output": output_path,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
    }


def _export_obsidian(
    g: nx.DiGraph,
    store: UnifiedStore,
    output_path: str,
) -> dict[str, Any]:
    """Export as Obsidian vault (markdown with wikilinks)."""
    output_dir = Path(output_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    count = 0

    index_content = "# Knowledge Graph Index\n\n"
    index_content += f"**{g.number_of_nodes()} nodes, {g.number_of_edges()} edges**\n\n"

    top_nodes = sorted(
        g.nodes(data=True),
        key=lambda x: g.degree(x[0]),
        reverse=True
    )[:20]

    index_content += "## Top Nodes\n"
    for node, data in top_nodes:
        label = data.get("name", node)
        index_content += f"- [[{label}]] (degree: {g.degree(node)})\n"

    (output_dir / "index.md").write_text(index_content, encoding="utf-8")
    count += 1

    for node, data in g.nodes(data=True):
        label = data.get("name", node)
        safe_label = "".join(c if c.isalnum() else "_" for c in label)[:50]
        file_path = output_dir / f"{safe_label}.md"

        content = f"# {label}\n\n"
        content += f"**Kind:** {data.get('kind', 'Unknown')}\n"
        content += f"**File:** {data.get('file_path', 'N/A')}\n"
        content += f"**Pipeline:** {data.get('pipeline', 'N/A')}\n"
        content += f"**Degree:** {g.degree(node)}\n\n"

        successors = list(g.successors(node))[:10]
        if successors:
            content += "## References\n"
            for succ in successors:
                succ_label = g.nodes[succ].get("name", succ)
                content += f"- [[{succ_label}]]\n"

        predecessors = list(g.predecessors(node))[:10]
        if predecessors:
            content += "## Referenced By\n"
            for pred in predecessors:
                pred_label = g.nodes[pred].get("name", pred)
                content += f"- [[{pred_label}]]\n"

        file_path.write_text(content, encoding="utf-8")
        count += 1

    return {
        "format": "obsidian",
        "output": str(output_dir),
        "notes_written": count,
        "nodes": g.number_of_nodes(),
        "edges": g.number_of_edges(),
    }


def _export_svg(
    g: nx.DiGraph,
    output_path: str,
) -> dict[str, Any]:
    """Export as SVG via matplotlib."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return {"error": "matplotlib not installed. Install with: pip install gathon[svg]"}

    if g.number_of_nodes() < 2:
        return {"error": "Graph too small for visualization"}

    try:
        pos = nx.spring_layout(g, seed=42, k=2.0 / (len(g) ** 0.5 + 1), iterations=50)

        fig, ax = plt.subplots(figsize=(20, 14), dpi=100)

        max_degree = max(dict(g.degree()).values()) if g.number_of_nodes() > 0 else 1
        node_sizes = [300 + 1200 * (g.degree(node) / max(max_degree, 1)) for node in g.nodes()]

        colors = []
        for node in g.nodes():
            ft = g.nodes[node].get("file_type", "code")
            if ft == "code":
                colors.append("#4A90D9")
            elif ft == "document":
                colors.append("#27AE60")
            else:
                colors.append("#95A5A6")

        nx.draw_networkx_nodes(g, pos, node_size=node_sizes, node_color=colors, ax=ax, alpha=0.8)
        nx.draw_networkx_edges(g, pos, ax=ax, alpha=0.5, arrows=True, arrowsize=10)

        labels = {node: g.nodes[node].get("name", node)[:10] for node in g.nodes()}
        nx.draw_networkx_labels(g, pos, labels, font_size=8, ax=ax)

        ax.set_title(f"Gathon Knowledge Graph ({g.number_of_nodes()} nodes, {g.number_of_edges()} edges)", fontsize=16)
        ax.axis("off")
        plt.tight_layout()
        plt.savefig(output_path, format="svg", bbox_inches="tight")
        plt.close()

        return {
            "format": "svg",
            "output": output_path,
            "nodes": g.number_of_nodes(),
            "edges": g.number_of_edges(),
        }
    except Exception as exc:
        return {"error": f"SVG export failed: {exc}"}
