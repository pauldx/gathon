"""Query & search tools: query_graph, semantic_search, get_node, etc.

Progressive disclosure: detail_level="index" returns compact results
(~50 tok/result). detail_level="full" inlines node details (~200 tok/result).
Default is "index" — agent calls get_node_detail for specifics.
"""

from __future__ import annotations

from typing import Any

import networkx as nx

from gathon.store import UnifiedStore


def query_graph(
    store: UnifiedStore,
    target: str,
    pattern: str = "callers_of",
    max_depth: int = 2,
    mode: str = "structural",
    detail_level: str = "index",
) -> dict[str, Any]:
    """Query graph relationships. Supports gathon patterns and BFS/DFS.

    detail_level="index": edge kind + endpoints only.
    detail_level="full": adds node details for each endpoint.
    """
    if mode == "bfs" or mode == "dfs":
        return _graph_traversal(store, target, mode, max_depth)

    node = store.get_node(target)
    if not node:
        return {"error": f"Node not found: {target}", "results": []}

    results: list[dict[str, Any]] = []

    if pattern == "callers_of":
        for e in store.get_edges_by_target(target):
            if e.kind in ("CALLS", "REFERENCES"):
                results.append(_edge_dict(e, "caller"))
    elif pattern == "callees_of":
        for e in store.get_edges_by_source(target):
            if e.kind in ("CALLS", "REFERENCES"):
                results.append(_edge_dict(e, "callee"))
    elif pattern == "imports_of":
        for e in store.get_edges_by_source(target):
            if e.kind == "IMPORTS_FROM":
                results.append(_edge_dict(e, "import"))
    elif pattern == "tests_for":
        for e in store.get_edges_by_target(target):
            if e.kind == "TESTED_BY":
                results.append(_edge_dict(e, "test"))
    elif pattern == "contains":
        for e in store.get_edges_by_source(target):
            if e.kind == "CONTAINS":
                results.append(_edge_dict(e, "child"))
    elif pattern == "references":
        for e in store.get_edges_by_source(target):
            results.append(_edge_dict(e, "ref"))
        for e in store.get_edges_by_target(target):
            results.append(_edge_dict(e, "ref"))
    else:
        return {"error": f"Unknown pattern: {pattern}"}

    if detail_level == "full":
        results = _enrich_edge_results(store, results)

    return {
        "target": target,
        "pattern": pattern,
        "count": len(results),
        "detail_level": detail_level,
        "results": results,
    }


def _graph_traversal(
    store: UnifiedStore,
    start: str,
    mode: str,
    max_depth: int,
) -> dict[str, Any]:
    """BFS/DFS traversal via NetworkX."""
    g = store.build_networkx_graph()
    if start not in g:
        return {"error": f"Node not found: {start}", "results": []}

    if mode == "bfs":
        visited = list(nx.bfs_tree(g, start, depth_limit=max_depth))
    else:
        visited = list(nx.dfs_tree(g, start, depth_limit=max_depth))

    results = []
    for qn in visited:
        data = g.nodes[qn]
        results.append({
            "qualified_name": qn,
            "kind": data.get("kind", ""),
            "name": data.get("name", ""),
            "file_type": data.get("file_type", ""),
        })

    return {
        "start": start,
        "mode": mode,
        "depth": max_depth,
        "count": len(results),
        "results": results,
    }


def semantic_search(
    store: UnifiedStore,
    query: str,
    limit: int = 20,
    detail_level: str = "index",
) -> dict[str, Any]:
    """FTS5 search across all node types.

    detail_level="index": compact (qualified_name, kind, file_path).
    detail_level="full": includes label, language, line range, pipeline.
    """
    results = store.search_nodes(query, limit=limit)

    if detail_level == "full":
        items = []
        for n in results:
            item: dict[str, Any] = {
                "qualified_name": n.qualified_name,
                "kind": n.kind,
                "name": n.name,
                "file_path": n.file_path,
            }
            row = store._conn.execute(
                "SELECT label, file_type, language, line_start,"
                " line_end, pipeline FROM nodes"
                " WHERE qualified_name = ?",
                (n.qualified_name,),
            ).fetchone()
            if row:
                item.update({
                    "label": row[0],
                    "file_type": row[1],
                    "language": row[2],
                    "line_start": row[3],
                    "line_end": row[4],
                    "pipeline": row[5],
                })
            items.append(item)
    else:
        items = [
            {
                "qualified_name": n.qualified_name,
                "kind": n.kind,
                "name": n.name,
                "file_path": n.file_path,
            }
            for n in results
        ]

    return {
        "query": query,
        "count": len(items),
        "detail_level": detail_level,
        "results": items,
    }


def get_node_detail(
    store: UnifiedStore,
    qualified_name: str,
) -> dict[str, Any]:
    """Full node details including gathon fields."""
    node = store.get_node(qualified_name)
    if not node:
        return {"error": f"Not found: {qualified_name}"}

    row = store._conn.execute(
        "SELECT label, file_type, source_url, confidence,"
        " confidence_score, pipeline, author"
        " FROM nodes WHERE qualified_name = ?",
        (qualified_name,),
    ).fetchone()

    result: dict[str, Any] = {
        "qualified_name": node.qualified_name,
        "kind": node.kind,
        "name": node.name,
        "file_path": node.file_path,
        "line_start": node.line_start,
        "line_end": node.line_end,
        "language": node.language,
        "is_test": node.is_test,
    }
    if row:
        result.update({
            "label": row[0],
            "file_type": row[1],
            "source_url": row[2],
            "confidence": row[3],
            "confidence_score": row[4],
            "pipeline": row[5],
            "author": row[6],
        })

    return result


def get_neighbors(
    store: UnifiedStore,
    qualified_name: str,
    relation_filter: str | None = None,
    detail_level: str = "index",
) -> dict[str, Any]:
    """Get all neighbors of a node, optionally filtered by edge kind.

    detail_level="index": qualified_name + edge_kind + direction.
    detail_level="full": adds node kind, file_path, file_type.
    """
    outgoing = store.get_edges_by_source(qualified_name)
    incoming = store.get_edges_by_target(qualified_name)

    neighbors: list[dict[str, Any]] = []
    for e in outgoing:
        if relation_filter and e.kind != relation_filter:
            continue
        item: dict[str, Any] = {
            "qualified_name": e.target_qualified,
            "edge_kind": e.kind,
            "direction": "outgoing",
        }
        if detail_level == "full":
            _enrich_node_dict(store, item, e.target_qualified)
        neighbors.append(item)
    for e in incoming:
        if relation_filter and e.kind != relation_filter:
            continue
        item = {
            "qualified_name": e.source_qualified,
            "edge_kind": e.kind,
            "direction": "incoming",
        }
        if detail_level == "full":
            _enrich_node_dict(store, item, e.source_qualified)
        neighbors.append(item)

    return {
        "node": qualified_name,
        "count": len(neighbors),
        "detail_level": detail_level,
        "neighbors": neighbors,
    }


def shortest_path(
    store: UnifiedStore,
    source: str,
    target: str,
) -> dict[str, Any]:
    """Find shortest path between two nodes via NetworkX."""
    g = store.build_networkx_graph()
    ug = g.to_undirected()

    if source not in ug or target not in ug:
        missing = []
        if source not in ug:
            missing.append(source)
        if target not in ug:
            missing.append(target)
        return {"error": f"Not found: {', '.join(missing)}"}

    try:
        path = nx.shortest_path(ug, source, target)
    except nx.NetworkXNoPath:
        return {
            "source": source, "target": target,
            "connected": False, "path": [],
        }

    return {
        "source": source,
        "target": target,
        "connected": True,
        "length": len(path) - 1,
        "path": list(path),
    }


def _enrich_node_dict(
    store: UnifiedStore,
    item: dict[str, Any],
    qualified_name: str,
) -> None:
    """Add node details to an existing result dict (in-place)."""
    row = store._conn.execute(
        "SELECT kind, name, file_path, file_type, language"
        " FROM nodes WHERE qualified_name = ?",
        (qualified_name,),
    ).fetchone()
    if row:
        item["kind"] = row[0]
        item["name"] = row[1]
        item["file_path"] = row[2]
        item["file_type"] = row[3]
        item["language"] = row[4]


def _enrich_edge_results(
    store: UnifiedStore,
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Enrich edge results with node details for both endpoints."""
    for item in results:
        peer = item.get("target") or item.get("source", "")
        _enrich_node_dict(store, item, peer)
    return results


def _edge_dict(edge: Any, role: str) -> dict[str, Any]:
    return {
        "role": role,
        "kind": edge.kind,
        "source": edge.source_qualified,
        "target": edge.target_qualified,
        "file_path": edge.file_path,
    }
