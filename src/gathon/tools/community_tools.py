"""Community tools: list, get, architecture overview."""

from __future__ import annotations

from typing import Any

from gathon.store import UnifiedStore


def list_communities(
    store: UnifiedStore,
    sort_by: str = "size",
    min_size: int = 0,
    detail_level: str = "standard",
) -> dict[str, Any]:
    """List detected communities."""
    try:
        from gathon.code_graph.communities import (
            get_architecture_overview,
        )
        overview = get_architecture_overview(store)
        comms = overview.get("communities", [])
        if min_size:
            comms = [c for c in comms if c.get("size", 0) >= min_size]
        return {
            "count": len(comms),
            "communities": comms,
            "sort_by": sort_by,
        }
    except ImportError:
        return {"error": "communities module not available"}


def get_community(
    store: UnifiedStore,
    community_id: int | None = None,
    community_name: str | None = None,
) -> dict[str, Any]:
    """Get community details with members."""
    rows = store._conn.execute(
        "SELECT id, name, level, size, dominant_language,"
        " description FROM communities"
        " WHERE id = ? OR name = ?",
        (community_id, community_name),
    ).fetchall()

    if not rows:
        return {"error": "Community not found"}

    row = rows[0]
    cid = row[0]
    members = store._conn.execute(
        "SELECT qualified_name, kind, name FROM nodes"
        " WHERE community_id = ?",
        (cid,),
    ).fetchall()

    return {
        "id": cid,
        "name": row[1],
        "level": row[2],
        "size": row[3],
        "dominant_language": row[4],
        "description": row[5],
        "members": [
            {"qualified_name": m[0], "kind": m[1], "name": m[2]}
            for m in members
        ],
    }


def get_architecture_overview(
    store: UnifiedStore,
) -> dict[str, Any]:
    """High-level architecture from community structure."""
    try:
        from gathon.code_graph.communities import (
            get_architecture_overview as _gao,
        )
        return _gao(store)
    except ImportError:
        stats = store.get_unified_stats()
        return {
            "summary": "Architecture overview (basic)",
            "stats": stats,
        }
