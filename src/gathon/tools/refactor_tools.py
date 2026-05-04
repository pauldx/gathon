"""Refactoring tools: rename, dead_code, suggest, find_large."""

from __future__ import annotations

from typing import Any

from gathon.store import UnifiedStore


def refactor(
    store: UnifiedStore,
    mode: str = "rename",
    old_name: str | None = None,
    new_name: str | None = None,
    kind: str | None = None,
    file_pattern: str | None = None,
) -> dict[str, Any]:
    """Refactoring operations."""
    try:
        from gathon.code_graph.refactor import (
            find_dead_code,
            rename_preview,
            suggest_refactors,
        )
    except ImportError:
        return {"error": "refactor module not available"}

    if mode == "rename":
        if not old_name or not new_name:
            return {"error": "rename requires old_name and new_name"}
        return rename_preview(store, old_name, new_name)
    elif mode == "dead_code":
        return find_dead_code(store, kind=kind, file_pattern=file_pattern)
    elif mode == "suggest":
        return suggest_refactors(store)
    else:
        return {"error": f"Unknown refactor mode: {mode}"}


def find_large_functions(
    store: UnifiedStore,
    min_lines: int = 50,
    kind: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Find functions/classes exceeding line threshold."""
    nodes = store.get_nodes_by_size(
        min_lines=min_lines, kind=kind, limit=limit,
    )
    return {
        "count": len(nodes),
        "min_lines": min_lines,
        "results": [
            {
                "qualified_name": n.qualified_name,
                "kind": n.kind,
                "name": n.name,
                "file_path": n.file_path,
                "lines": n.line_end - n.line_start,
            }
            for n in nodes
        ],
    }
