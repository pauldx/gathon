"""Analysis tools: stats, god_nodes, bridge_nodes, gaps, surprises."""

from __future__ import annotations

from typing import Any

import networkx as nx

from gathon.store import UnifiedStore


def list_graph_stats(
    store: UnifiedStore,
    scope: str = "all",
) -> dict[str, Any]:
    """Unified stats: nodes by kind, confidence, pipeline, file_type."""
    stats = store.get_unified_stats()
    if scope == "code":
        stats["note"] = "Filtered to code pipeline"
    elif scope == "document":
        stats["note"] = "Filtered to document pipeline"
    return stats


def god_nodes(
    store: UnifiedStore,
    top_n: int = 10,
    scope: str = "all",
) -> dict[str, Any]:
    """Top-N most connected nodes by degree."""
    g = store.build_networkx_graph()

    if scope == "code":
        nodes = [
            n for n, d in g.nodes(data=True)
            if d.get("file_type", "code") == "code"
        ]
    elif scope == "document":
        nodes = [
            n for n, d in g.nodes(data=True)
            if d.get("file_type") in ("document", "paper")
        ]
    else:
        nodes = list(g.nodes())

    sub = g.subgraph(nodes)
    degree_list = sorted(
        sub.degree(), key=lambda x: x[1], reverse=True,
    )[:top_n]

    return {
        "scope": scope,
        "count": len(degree_list),
        "nodes": [
            {
                "qualified_name": qn,
                "degree": deg,
                "kind": g.nodes[qn].get("kind", ""),
                "name": g.nodes[qn].get("name", ""),
            }
            for qn, deg in degree_list
        ],
    }


def get_bridge_nodes(
    store: UnifiedStore,
    top_n: int = 10,
) -> dict[str, Any]:
    """Nodes with highest betweenness centrality — bridges."""
    g = store.build_networkx_graph()
    if g.number_of_nodes() == 0:
        return {"count": 0, "nodes": []}

    ug = g.to_undirected()
    bc = nx.betweenness_centrality(ug)
    top = sorted(bc.items(), key=lambda x: x[1], reverse=True)[:top_n]

    return {
        "count": len(top),
        "nodes": [
            {
                "qualified_name": qn,
                "betweenness": round(score, 4),
                "kind": g.nodes[qn].get("kind", ""),
            }
            for qn, score in top
        ],
    }


def get_surprising_connections(
    store: UnifiedStore,
    top_n: int = 10,
) -> dict[str, Any]:
    """Edges crossing code ↔ document boundaries."""
    g = store.build_networkx_graph()
    surprises: list[dict[str, Any]] = []

    for src, tgt, data in g.edges(data=True):
        src_type = g.nodes[src].get("file_type", "code")
        tgt_type = g.nodes[tgt].get("file_type", "code")
        if src_type != tgt_type:
            surprises.append({
                "source": src,
                "target": tgt,
                "source_type": src_type,
                "target_type": tgt_type,
                "relation": data.get("relation", ""),
            })

    return {
        "count": len(surprises[:top_n]),
        "connections": surprises[:top_n],
    }


def get_knowledge_gaps(
    store: UnifiedStore,
) -> dict[str, Any]:
    """Nodes with low confidence or missing connections."""
    g = store.build_networkx_graph()
    isolates = list(nx.isolates(g))

    low_conf_rows = store._conn.execute(
        "SELECT qualified_name, kind, confidence, confidence_score"
        " FROM nodes WHERE confidence_score < 0.5"
    ).fetchall()

    return {
        "isolated_nodes": len(isolates),
        "low_confidence_nodes": len(low_conf_rows),
        "isolates": [
            {"qualified_name": qn, "kind": g.nodes[qn].get("kind", "")}
            for qn in isolates[:20]
        ],
        "low_confidence": [
            {
                "qualified_name": r[0], "kind": r[1],
                "confidence": r[2], "score": r[3],
            }
            for r in low_conf_rows[:20]
        ],
    }
