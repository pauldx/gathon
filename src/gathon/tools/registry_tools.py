"""Registry tools: traverse_graph, cross_repo_search."""

from __future__ import annotations

from typing import Any

import networkx as nx

from gathon.store import UnifiedStore


def traverse_graph(
    store: UnifiedStore,
    query: str,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
) -> dict[str, Any]:
    """Free-form BFS/DFS with token budget."""
    results = store.search_nodes(query, limit=5)
    if not results:
        return {"error": f"No nodes matching: {query}", "results": []}

    start = results[0].qualified_name
    g = store.build_networkx_graph()

    if start not in g:
        return {"error": f"Node not in graph: {start}"}

    if mode == "dfs":
        visited = list(nx.dfs_tree(g, start, depth_limit=depth))
    else:
        visited = list(nx.bfs_tree(g, start, depth_limit=depth))

    output: list[dict[str, Any]] = []
    tokens_used = 0
    for qn in visited:
        entry = {
            "qualified_name": qn,
            "kind": g.nodes[qn].get("kind", ""),
            "name": g.nodes[qn].get("name", ""),
        }
        tokens_used += len(qn) // 4 + 10
        if tokens_used > token_budget:
            break
        output.append(entry)

    return {
        "start_node": start,
        "mode": mode,
        "depth": depth,
        "nodes_visited": len(output),
        "truncated": tokens_used > token_budget,
        "traversal": output,
    }


def cross_repo_search(
    query: str,
    kind: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search across registered repos — placeholder."""
    return {
        "query": query,
        "kind": kind,
        "results": [],
        "note": "Multi-repo registry not yet implemented",
    }
