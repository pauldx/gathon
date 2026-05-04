"""Impact & review context tools."""

from __future__ import annotations

from typing import Any

from gathon.store import UnifiedStore


def get_minimal_context(
    store: UnifiedStore,
    task: str = "",
) -> dict[str, Any]:
    """Ultra-compact graph summary for token-efficient orientation."""
    stats = store.get_unified_stats()
    return {
        "task": task,
        "total_nodes": stats["total_nodes"],
        "total_edges": stats["total_edges"],
        "files": stats["files_count"],
        "languages": stats["languages"],
        "nodes_by_kind": stats["nodes_by_kind"],
        "nodes_by_pipeline": stats["nodes_by_pipeline"],
        "nodes_by_file_type": stats["nodes_by_file_type"],
        "next_tool_suggestions": [
            "query_graph", "semantic_search", "get_impact_radius",
        ],
    }


def get_impact_radius(
    store: UnifiedStore,
    changed_files: list[str],
    max_depth: int = 3,
    max_nodes: int = 200,
) -> dict[str, Any]:
    """Blast radius for code AND document nodes."""
    return store.get_impact_radius(
        changed_files, max_depth=max_depth, max_nodes=max_nodes,
    )


def get_review_context(
    store: UnifiedStore,
    file_path: str,
    detail_level: str = "minimal",
) -> dict[str, Any]:
    """Source context for review — node summaries per file."""
    nodes = store.get_nodes_by_file(file_path)
    if not nodes:
        return {"file_path": file_path, "nodes": [], "count": 0}

    result_nodes = []
    for n in nodes:
        entry: dict[str, Any] = {
            "qualified_name": n.qualified_name,
            "kind": n.kind,
            "name": n.name,
            "line_start": n.line_start,
            "line_end": n.line_end,
        }
        if detail_level != "minimal":
            entry["is_test"] = n.is_test
            entry["language"] = n.language
            callers = store.get_edges_by_target(n.qualified_name)
            entry["caller_count"] = len(callers)
        result_nodes.append(entry)

    return {
        "file_path": file_path,
        "count": len(result_nodes),
        "nodes": result_nodes,
    }


def detect_changes(
    store: UnifiedStore,
    changed_files: list[str],
) -> dict[str, Any]:
    """Risk-scored change analysis — wraps changes module."""
    try:
        from gathon.code_graph.changes import analyze_changes
        return analyze_changes(store, changed_files)
    except ImportError:
        return {
            "changed_files": changed_files,
            "error": "changes module not available",
        }


def get_affected_flows(
    store: UnifiedStore,
    changed_files: list[str],
) -> dict[str, Any]:
    """Which execution flows are impacted by changed files."""
    try:
        from gathon.code_graph.flows import get_affected_flows as _gaf
        return _gaf(store, changed_files)
    except ImportError:
        return {"error": "flows module not available"}
