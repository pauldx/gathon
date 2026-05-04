"""Review tools: review_context, detect_changes, affected_flows."""

from __future__ import annotations

from typing import Any

from gathon.store import UnifiedStore


def get_review_context(
    store: UnifiedStore,
    changed_files: list[str],
    include_source: bool = True,
    max_depth: int = 2,
    detail_level: str = "standard",
) -> dict[str, Any]:
    """Review context combining impact + source snippets."""
    impact = store.get_impact_radius(
        changed_files, max_depth=max_depth,
    )

    file_contexts: list[dict[str, Any]] = []
    for fp in changed_files:
        nodes = store.get_nodes_by_file(fp)
        ctx: dict[str, Any] = {
            "file_path": fp,
            "node_count": len(nodes),
            "nodes": [
                {
                    "qualified_name": n.qualified_name,
                    "kind": n.kind,
                    "name": n.name,
                    "lines": f"{n.line_start}-{n.line_end}",
                }
                for n in nodes
            ],
        }
        file_contexts.append(ctx)

    return {
        "changed_files": changed_files,
        "impact": impact,
        "file_contexts": file_contexts,
        "detail_level": detail_level,
    }
