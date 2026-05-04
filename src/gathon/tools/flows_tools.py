"""Flow tools: list_flows, get_flow."""

from __future__ import annotations

from typing import Any

from gathon.store import UnifiedStore


def list_flows(
    store: UnifiedStore,
    sort_by: str = "criticality",
    limit: int = 50,
) -> dict[str, Any]:
    """List detected execution flows."""
    rows = store._conn.execute(
        "SELECT id, name, depth, node_count, file_count,"
        " criticality FROM flows ORDER BY criticality DESC"
        " LIMIT ?",
        (limit,),
    ).fetchall()

    flows = [
        {
            "id": r[0], "name": r[1], "depth": r[2],
            "node_count": r[3], "file_count": r[4],
            "criticality": r[5],
        }
        for r in rows
    ]

    return {"count": len(flows), "flows": flows, "sort_by": sort_by}


def get_flow(
    store: UnifiedStore,
    flow_id: int | None = None,
    flow_name: str | None = None,
) -> dict[str, Any]:
    """Get flow details with path."""
    row = store._conn.execute(
        "SELECT id, name, depth, node_count, file_count,"
        " criticality, path_json FROM flows"
        " WHERE id = ? OR name = ?",
        (flow_id, flow_name),
    ).fetchone()

    if not row:
        return {"error": "Flow not found"}

    import json
    path = json.loads(row[6]) if row[6] else []

    return {
        "id": row[0], "name": row[1], "depth": row[2],
        "node_count": row[3], "file_count": row[4],
        "criticality": row[5], "path": path,
    }
