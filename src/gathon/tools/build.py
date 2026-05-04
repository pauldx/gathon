"""Build & ingest tools: build_graph, run_postprocess, ingest_url, embed_graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_graph(
    repo_root: str,
    db_path: str | None = None,
    incremental: bool = True,
    base: str = "HEAD~1",
) -> dict[str, Any]:
    """Build or update unified graph for a repo. Adaptive routing."""
    from gathon.incremental import full_build, incremental_update
    from gathon.store import UnifiedStore

    root = Path(repo_root).resolve()
    db = db_path or str(root / ".gathon" / "graph.db")
    Path(db).parent.mkdir(parents=True, exist_ok=True)

    store = UnifiedStore(db)
    try:
        if incremental:
            result = incremental_update(root, store, base=base)
        else:
            result = full_build(root, store)
        stats = store.get_unified_stats()
        result["stats"] = stats
        return result
    finally:
        store.close()


def run_postprocess(
    db_path: str,
) -> dict[str, Any]:
    """Run post-processing: flows, communities, FTS, signatures."""
    from gathon.code_graph.communities import detect_communities
    from gathon.code_graph.flows import detect_flows

    from gathon.store import UnifiedStore

    store = UnifiedStore(db_path)
    try:
        flow_result = detect_flows(store)
        comm_result = detect_communities(store)
        store.commit()
        return {
            "flows": flow_result,
            "communities": comm_result,
        }
    finally:
        store.close()


def ingest_url(
    url: str,
    db_path: str,
) -> dict[str, Any]:
    """Ingest content from URL."""
    from gathon.multimodal_graph.url_parser import parse_url
    from gathon.schema import Pipeline
    from gathon.store import UnifiedStore

    nodes, edges = parse_url(url)

    store = UnifiedStore(db_path)
    try:
        store.store_unified_file(
            url,
            nodes,
            edges,
            pipeline=Pipeline.GATHON_URL,
        )
        store.commit()
        return {
            "url": url,
            "nodes": len(nodes),
            "edges": len(edges),
        }
    finally:
        store.close()
