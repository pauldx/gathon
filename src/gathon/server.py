"""FastMCP server exposing 58 unified graph tools."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

from gathon.compress import Intensity, compress_tool_response
from gathon.store import UnifiedStore
from gathon.telemetry import TelemetryLogger
from gathon.tokens import attach_token_meta

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "gathon",
    instructions=(
        "গাঁথন — Unified adaptive knowledge graph engine. "
        "Merges code structural graphs with multi-modal "
        "knowledge graphs into a single queryable store."
    ),
)

_default_repo_root: str | None = None
_compression_intensity: str = os.environ.get(
    "GATHON_COMPRESS", Intensity.OFF,
)


def set_compression(intensity: str) -> None:
    """Set compression intensity: off, lite, full, ultra."""
    global _compression_intensity
    _compression_intensity = intensity


def _get_telemetry() -> TelemetryLogger | None:
    """Get telemetry logger if DB exists."""
    try:
        _, root = _get_store_raw()
        db_path = root / ".gathon" / "graph.db"
        if db_path.exists():
            import sqlite3
            conn = sqlite3.connect(str(db_path))
            return TelemetryLogger(conn)
    except Exception:
        pass
    return None


def _get_store_raw() -> tuple[None, Path]:
    """Get root path without opening store."""
    root = Path(_default_repo_root or ".").resolve()
    return None, root


def _compressed(
    data: dict[str, Any],
    tool_name: str = "",
) -> dict[str, Any]:
    """Apply compression + token meta + telemetry logging."""
    result = compress_tool_response(data, _compression_intensity)
    result = attach_token_meta(result)

    if _compression_intensity != Intensity.OFF and tool_name:
        try:
            tl = _get_telemetry()
            if tl:
                tl.log_compression(
                    tool_name, data, result, _compression_intensity,
                )
        except Exception:
            pass

    return result


def _log_disclosure(
    tool_name: str,
    detail_level: str,
    data: dict[str, Any],
) -> None:
    """Log progressive disclosure choice to telemetry."""
    try:
        tl = _get_telemetry()
        if tl:
            from gathon.tokens import estimate_tokens
            tl.log_disclosure(tool_name, detail_level, estimate_tokens(data))
    except Exception:
        pass


def _get_store(repo_root: str | None = None) -> tuple[UnifiedStore, Path]:
    root = Path(repo_root or _default_repo_root or ".").resolve()
    db_dir = root / ".gathon"
    db_dir.mkdir(parents=True, exist_ok=True)
    return UnifiedStore(str(db_dir / "graph.db")), root


# === Build & Ingest (4) ===


@mcp.tool()
async def build_graph(
    repo_root: str | None = None,
    full_rebuild: bool = False,
    base: str = "HEAD~1",
) -> dict[str, Any]:
    """Build or update unified graph. Adaptive routing to gathon/OpenAPI/config pipelines."""
    from gathon.tools.build import build_graph as _bg
    return _compressed(_bg(
        repo_root=repo_root or _default_repo_root or ".",
        incremental=not full_rebuild,
        base=base,
    ), tool_name="build_graph")


@mcp.tool()
async def run_postprocess(
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Run post-processing: flows, communities, FTS, signatures."""
    store, root = _get_store(repo_root)
    try:
        from gathon.tools.build import run_postprocess as _rp
        return _compressed(_rp(str(root / ".gathon" / "graph.db")), tool_name="run_postprocess")
    finally:
        store.close()


@mcp.tool()
def ingest_url(
    url: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Ingest content from URL into graph."""
    store, root = _get_store(repo_root)
    try:
        from gathon.tools.build import ingest_url as _iu
        return _compressed(_iu(url, str(root / ".gathon" / "graph.db")), tool_name="ingest_url")
    finally:
        store.close()


# === Query & Search (5) ===


@mcp.tool()
def query_graph(
    target: str,
    pattern: str = "callers_of",
    max_depth: int = 2,
    mode: str = "structural",
    detail_level: str = "index",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Query graph relationships. detail_level: index (compact) or full (with node details)."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.query import query_graph as _qg
        result = _qg(store, target, pattern, max_depth, mode, detail_level)
        _log_disclosure("query_graph", detail_level, result)
        return _compressed(result, tool_name="query_graph")
    finally:
        store.close()


@mcp.tool()
def semantic_search(
    query: str,
    limit: int = 20,
    detail_level: str = "index",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """FTS5 search across all node types. detail_level: index (compact) or full."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.query import semantic_search as _ss
        result = _ss(store, query, limit, detail_level)
        _log_disclosure("semantic_search", detail_level, result)
        return _compressed(result, tool_name="semantic_search")
    finally:
        store.close()


@mcp.tool()
def get_node(
    qualified_name: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Full node details including gathon fields (file_type, confidence, pipeline)."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.query import get_node_detail
        return _compressed(get_node_detail(store, qualified_name), tool_name="get_node")
    finally:
        store.close()


@mcp.tool()
def get_neighbors(
    qualified_name: str,
    relation_filter: str | None = None,
    detail_level: str = "index",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Get neighbors. detail_level: index (compact) or full (with node details)."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.query import get_neighbors as _gn
        result = _gn(store, qualified_name, relation_filter, detail_level)
        _log_disclosure("get_neighbors", detail_level, result)
        return _compressed(result, tool_name="get_neighbors")
    finally:
        store.close()


@mcp.tool()
def shortest_path(
    source: str,
    target: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Shortest path between any two nodes — works across code/doc boundaries."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.query import shortest_path as _sp
        return _compressed(_sp(store, source, target), tool_name="shortest_path")
    finally:
        store.close()


# === Impact & Review (5) ===


@mcp.tool()
def get_minimal_context(
    task: str = "",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Ultra-compact graph summary (~100 tokens). Start here."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.context import get_minimal_context as _gmc
        return _compressed(_gmc(store, task), tool_name="get_minimal_context")
    finally:
        store.close()


@mcp.tool()
def get_impact_radius(
    changed_files: list[str] | None = None,
    max_depth: int = 3,
    max_nodes: int = 200,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Blast radius for code AND document node changes."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.context import get_impact_radius as _gir
        return _compressed(
            _gir(store, changed_files or [], max_depth, max_nodes),
            tool_name="get_impact_radius",
        )
    finally:
        store.close()


@mcp.tool()
def get_review_context(
    changed_files: list[str] | None = None,
    max_depth: int = 2,
    detail_level: str = "standard",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Review context with impact + source node summaries."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.review import get_review_context as _grc
        return _compressed(
            _grc(
                store, changed_files or [], max_depth=max_depth,
                detail_level=detail_level,
            ),
            tool_name="get_review_context",
        )
    finally:
        store.close()


@mcp.tool()
def detect_changes(
    changed_files: list[str] | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Risk-scored change analysis including doc changes."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.context import detect_changes as _dc
        return _compressed(_dc(store, changed_files or []), tool_name="detect_changes")
    finally:
        store.close()


@mcp.tool()
def get_affected_flows(
    changed_files: list[str] | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Which execution flows are impacted by changes."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.context import get_affected_flows as _gaf
        return _compressed(_gaf(store, changed_files or []), tool_name="get_affected_flows")
    finally:
        store.close()


# === Flows & Architecture (5) ===


@mcp.tool()
def list_flows(
    sort_by: str = "criticality",
    limit: int = 50,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """List detected execution flows."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.flows_tools import list_flows as _lf
        return _compressed(_lf(store, sort_by, limit), tool_name="list_flows")
    finally:
        store.close()


@mcp.tool()
def get_flow(
    flow_id: int | None = None,
    flow_name: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Get flow details with execution path."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.flows_tools import get_flow as _gf
        return _compressed(_gf(store, flow_id, flow_name), tool_name="get_flow")
    finally:
        store.close()


@mcp.tool()
def list_communities(
    sort_by: str = "size",
    min_size: int = 0,
    detail_level: str = "standard",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """List code + document communities."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.community_tools import list_communities as _lc
        return _compressed(
            _lc(store, sort_by, min_size, detail_level),
            tool_name="list_communities",
        )
    finally:
        store.close()


@mcp.tool()
def get_community(
    community_id: int | None = None,
    community_name: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Get community details with member nodes."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.community_tools import get_community as _gc
        return _compressed(
            _gc(store, community_id, community_name),
            tool_name="get_community",
        )
    finally:
        store.close()


@mcp.tool()
def get_architecture_overview(
    repo_root: str | None = None,
) -> dict[str, Any]:
    """High-level architecture from community structure."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.community_tools import (
            get_architecture_overview as _gao,
        )
        return _compressed(_gao(store), tool_name="get_architecture_overview")
    finally:
        store.close()


# === Analysis (6) ===


@mcp.tool()
def list_graph_stats(
    scope: str = "all",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Unified stats: nodes by kind, confidence, pipeline, file_type."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.analysis import list_graph_stats as _lgs
        return _compressed(_lgs(store, scope), tool_name="list_graph_stats")
    finally:
        store.close()


@mcp.tool()
def god_nodes(
    top_n: int = 10,
    scope: str = "all",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Top-N most connected nodes. Scope: all, code, document."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.analysis import god_nodes as _gn
        return _compressed(_gn(store, top_n, scope), tool_name="god_nodes")
    finally:
        store.close()


@mcp.tool()
def get_bridge_nodes(
    top_n: int = 10,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Nodes with highest betweenness centrality — structural bridges."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.analysis import get_bridge_nodes as _gbn
        return _compressed(_gbn(store, top_n), tool_name="get_bridge_nodes")
    finally:
        store.close()


@mcp.tool()
def get_knowledge_gaps(
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Isolated nodes and low-confidence extractions."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.analysis import get_knowledge_gaps as _gkg
        return _compressed(_gkg(store), tool_name="get_knowledge_gaps")
    finally:
        store.close()


@mcp.tool()
def get_surprising_connections(
    top_n: int = 10,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Edges crossing code ↔ document boundaries."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.analysis import (
            get_surprising_connections as _gsc,
        )
        return _compressed(_gsc(store, top_n), tool_name="get_surprising_connections")
    finally:
        store.close()


@mcp.tool()
def get_suggested_questions(
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Auto-generated questions about the codebase."""
    store, _ = _get_store(repo_root)
    try:
        stats = store.get_unified_stats()
        questions = []
        if stats["total_nodes"] > 0:
            questions.append(
                "What are the most connected components?"
            )
            questions.append(
                "Which files cross code/doc boundaries?"
            )
        if stats.get("nodes_by_file_type", {}).get("api_spec"):
            questions.append(
                "How do API endpoints map to code?"
            )
        return _compressed(
            {"count": len(questions), "questions": questions},
            tool_name="get_suggested_questions",
        )
    finally:
        store.close()


# === Refactoring (3) ===


@mcp.tool()
def refactor(
    mode: str = "rename",
    old_name: str | None = None,
    new_name: str | None = None,
    kind: str | None = None,
    file_pattern: str | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Refactoring: rename preview, dead code detection, suggestions."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.refactor_tools import refactor as _r
        return _compressed(
            _r(store, mode, old_name, new_name, kind, file_pattern),
            tool_name="refactor",
        )
    finally:
        store.close()


@mcp.tool()
def find_large_functions(
    min_lines: int = 50,
    kind: str | None = None,
    limit: int = 50,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Find functions/classes exceeding line threshold."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.refactor_tools import (
            find_large_functions as _flf,
        )
        return _compressed(_flf(store, min_lines, kind, limit), tool_name="find_large_functions")
    finally:
        store.close()


# === Export (3) ===


@mcp.tool()
def export_graph(
    output_path: str,
    format: str = "json",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Export graph: json, graphml."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.export_tools import export_graph as _eg
        return _compressed(_eg(store, output_path, format), tool_name="export_graph")
    finally:
        store.close()


@mcp.tool()
def generate_wiki(
    output_dir: str = ".gathon/wiki",
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Generate markdown wiki from community structure."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.export_tools import generate_wiki as _gw
        return _compressed(_gw(store, output_dir), tool_name="generate_wiki")
    finally:
        store.close()


# === Registry (2) ===


@mcp.tool()
def traverse_graph(
    query: str,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Free-form BFS/DFS traversal with token budget."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.registry_tools import traverse_graph as _tg
        return _compressed(
            _tg(store, query, mode, depth, token_budget),
            tool_name="traverse_graph",
        )
    finally:
        store.close()


@mcp.tool()
def cross_repo_search(
    query: str,
    kind: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search across registered repos."""
    from gathon.tools.registry_tools import cross_repo_search as _crs
    return _compressed(_crs(query, kind, limit), tool_name="cross_repo_search")


# === Telemetry (1) ===


@mcp.tool()
def compression_stats(
    days: int = 7,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Token compression telemetry: savings summary, per-tool breakdown, disclosure stats, trend."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.telemetry import TelemetryStats
        stats = TelemetryStats(store._conn)
        return _compressed(stats.get_full_stats(days), tool_name="compression_stats")
    finally:
        store.close()


# === Sandbox (6) ===


@mcp.tool()
def ctx_execute(
    language: str = "shell",
    code: str = "",
    timeout: int = 30,
    intent: str | None = None,
) -> dict[str, Any]:
    """Execute code in isolated subprocess. Raw output stays sandboxed."""
    from gathon.sandbox import SandboxExecutor
    executor = SandboxExecutor()
    result = executor.execute(language, code, timeout=timeout, intent=intent)
    return _compressed({
        "stdout": result.stdout,
        "stderr": result.stderr if result.exit_code != 0 else "",
        "exit_code": result.exit_code,
        "language": result.language,
        "elapsed_ms": result.elapsed_ms,
        "raw_bytes": result.raw_bytes,
        "context_bytes": result.context_bytes,
        "indexed": result.indexed,
        "timed_out": result.timed_out,
        "capped": result.capped,
    }, tool_name="ctx_execute")


@mcp.tool()
def ctx_execute_file(
    file_path: str,
    timeout: int = 30,
    intent: str | None = None,
) -> dict[str, Any]:
    """Execute a file in sandbox — file content never enters context."""
    from gathon.sandbox import SandboxExecutor
    executor = SandboxExecutor()
    result = executor.execute_file(file_path, timeout=timeout, intent=intent)
    return _compressed({
        "stdout": result.stdout,
        "stderr": result.stderr if result.exit_code != 0 else "",
        "exit_code": result.exit_code,
        "language": result.language,
        "elapsed_ms": result.elapsed_ms,
        "raw_bytes": result.raw_bytes,
        "context_bytes": result.context_bytes,
        "indexed": result.indexed,
    }, tool_name="ctx_execute_file")


@mcp.tool()
def ctx_batch_execute(
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    """Run multiple commands in sandbox, auto-index outputs."""
    from gathon.sandbox import SandboxExecutor
    executor = SandboxExecutor()
    results = executor.batch_execute(commands)
    return _compressed({
        "count": len(results),
        "results": [
            {
                "stdout": r.stdout,
                "stderr": r.stderr if r.exit_code != 0 else "",
                "exit_code": r.exit_code,
                "language": r.language,
                "elapsed_ms": r.elapsed_ms,
                "raw_bytes": r.raw_bytes,
                "context_bytes": r.context_bytes,
                "indexed": r.indexed,
            }
            for r in results
        ],
        "total_raw_bytes": sum(r.raw_bytes for r in results),
        "total_context_bytes": sum(r.context_bytes for r in results),
    }, tool_name="ctx_batch_execute")


@mcp.tool()
def ctx_index(
    label: str,
    content: str,
    source_type: str = "text",
) -> dict[str, Any]:
    """Index content into FTS5 knowledge base for later search."""
    from gathon.sandbox import ContentStore
    store = ContentStore()
    source_id = store.index(label, content, source_type)
    stats = store.stats()
    return _compressed({
        "source_id": source_id,
        "label": label,
        "indexed_bytes": len(content),
        "total_sources": stats["source_count"],
        "total_chunks": stats["chunk_count"],
    }, tool_name="ctx_index")


@mcp.tool()
def ctx_search(
    query: str,
    limit: int = 5,
) -> dict[str, Any]:
    """Search indexed content via FTS5 with 3-tier fallback (porter → trigram → fuzzy)."""
    from gathon.sandbox import ContentStore
    store = ContentStore()
    results = store.search(query, limit=limit)
    return _compressed({
        "query": query,
        "count": len(results),
        "results": [
            {
                "source": r.source_label,
                "title": r.title,
                "snippet": r.snippet,
                "score": round(r.score, 3),
            }
            for r in results
        ],
    }, tool_name="ctx_search")


@mcp.tool()
def ctx_fetch_and_index(
    url: str,
    label: str | None = None,
) -> dict[str, Any]:
    """Fetch URL, convert HTML→text, chunk, and index into knowledge base."""
    from gathon.sandbox import ContentStore
    store = ContentStore()
    source_id = store.fetch_and_index(url, label)
    if source_id < 0:
        return _compressed({
            "error": f"Failed to fetch {url}",
            "source_id": -1,
        }, tool_name="ctx_fetch_and_index")
    stats = store.stats()
    return _compressed({
        "source_id": source_id,
        "url": url,
        "label": label or url,
        "total_sources": stats["source_count"],
        "total_chunks": stats["chunk_count"],
    }, tool_name="ctx_fetch_and_index")


# === Session (4) ===


@mcp.tool()
def session_events(
    session_id: str | None = None,
    priority_max: int = 3,
) -> dict[str, Any]:
    """View session events for continuity tracking."""
    from gathon.session import SessionDB
    from gathon.session.hooks import _get_project_dir, _get_session_id
    sid = session_id or _get_session_id()
    db = SessionDB(project_dir=_get_project_dir())
    try:
        events = db.get_events(sid, priority_max=priority_max)
        counts = db.get_event_counts(sid)
        return _compressed({
            "session_id": sid,
            "event_count": len(events),
            "by_type": counts,
            "recent": [
                {
                    "type": e.event_type,
                    "priority": e.priority,
                    "data": e.data,
                    "at": e.created_at,
                }
                for e in events[-20:]
            ],
        }, tool_name="session_events")
    finally:
        db.close()


@mcp.tool()
def session_snapshot(
    session_id: str | None = None,
) -> dict[str, Any]:
    """Build and return current session snapshot (compaction-safe context)."""
    from gathon.session import SessionDB, build_snapshot
    from gathon.session.hooks import _get_project_dir, _get_session_id
    sid = session_id or _get_session_id()
    db = SessionDB(project_dir=_get_project_dir())
    try:
        snapshot = build_snapshot(db, sid)
        return _compressed({
            "session_id": sid,
            "snapshot": snapshot,
            "size_bytes": len(snapshot.encode("utf-8")),
        }, tool_name="session_snapshot")
    finally:
        db.close()


@mcp.tool()
def sandbox_stats() -> dict[str, Any]:
    """Show sandbox knowledge base statistics."""
    from gathon.sandbox import ContentStore
    store = ContentStore()
    return _compressed(store.stats(), tool_name="sandbox_stats")


@mcp.tool()
def sandbox_purge() -> dict[str, Any]:
    """Wipe all indexed content from sandbox knowledge base."""
    from gathon.sandbox import ContentStore
    store = ContentStore()
    before = store.stats()
    store.purge()
    return _compressed({
        "purged_sources": before["source_count"],
        "purged_chunks": before["chunk_count"],
        "purged_bytes": before["total_bytes"],
    }, tool_name="sandbox_purge")


# === Symbols (7) ===


@mcp.tool()
def find_symbol(
    name: str,
    exact: bool = False,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Find symbol definition: file, line, signature. Batch: pass comma-separated names."""
    from gathon.symbols import SymbolIndex
    idx = SymbolIndex(project_root=repo_root or _default_repo_root or ".")
    try:
        names = [n.strip() for n in name.split(",")]
        all_results = []
        for n in names:
            symbols = idx.find_symbol(n, exact=exact)
            all_results.extend([
                {
                    "name": s.name,
                    "qualified_name": s.qualified_name,
                    "kind": s.kind,
                    "file_path": s.file_path,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                    "language": s.language,
                    "signature": s.signature,
                    "is_test": s.is_test,
                }
                for s in symbols
            ])
        return _compressed({
            "query": name,
            "count": len(all_results),
            "symbols": all_results,
        }, tool_name="find_symbol")
    finally:
        idx.close()


@mcp.tool()
def get_function_source(
    name: str,
    level: int = 0,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Get function source. level: 0=full, 1=sig+doc, 2=sig only."""
    from gathon.symbols import SymbolIndex
    idx = SymbolIndex(project_root=repo_root or _default_repo_root or ".")
    try:
        source = idx.get_function_source(name, level=level)
        return _compressed({
            "name": name,
            "level": level,
            "source": source,
        }, tool_name="get_function_source")
    finally:
        idx.close()


@mcp.tool()
def get_class_source(
    name: str,
    level: int = 0,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Get class source. level: 0=full, 1=sig+methods, 2=sig only."""
    from gathon.symbols import SymbolIndex
    idx = SymbolIndex(project_root=repo_root or _default_repo_root or ".")
    try:
        source = idx.get_class_source(name, level=level)
        return _compressed({
            "name": name,
            "level": level,
            "source": source,
        }, tool_name="get_class_source")
    finally:
        idx.close()


@mcp.tool()
def get_symbol_deps(
    name: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """What this symbol depends on (calls, imports, inherits)."""
    from gathon.symbols import SymbolIndex
    idx = SymbolIndex(project_root=repo_root or _default_repo_root or ".")
    try:
        deps = idx.get_dependencies(name)
        return _compressed({
            "symbol": name,
            "count": len(deps),
            "dependencies": [
                {"source": d.source_symbol, "target": d.target_symbol, "kind": d.kind}
                for d in deps
            ],
        }, tool_name="get_symbol_deps")
    finally:
        idx.close()


@mcp.tool()
def get_symbol_dependents(
    name: str,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Who depends on this symbol (callers, importers)."""
    from gathon.symbols import SymbolIndex
    idx = SymbolIndex(project_root=repo_root or _default_repo_root or ".")
    try:
        deps = idx.get_dependents(name)
        return _compressed({
            "symbol": name,
            "count": len(deps),
            "dependents": [
                {"source": d.source_symbol, "target": d.target_symbol, "kind": d.kind}
                for d in deps
            ],
        }, tool_name="get_symbol_dependents")
    finally:
        idx.close()


@mcp.tool()
def index_symbols(
    repo_root: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Index/reindex project symbols via tree-sitter."""
    from gathon.symbols import SymbolIndex
    root = repo_root or _default_repo_root or "."
    idx = SymbolIndex(project_root=root)
    try:
        idx.index_project(root)
        return _compressed(idx.stats(), tool_name="index_symbols")
    finally:
        idx.close()


@mcp.tool()
def symbol_stats(
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Symbol index statistics: counts, languages, stale files."""
    from gathon.symbols import SymbolIndex
    root = repo_root or _default_repo_root or "."
    idx = SymbolIndex(project_root=root)
    try:
        s = idx.stats()
        stale = idx.get_stale_files(root)
        s["stale_files"] = len(stale)
        return _compressed(s, tool_name="symbol_stats")
    finally:
        idx.close()


# === Memory (6) ===


@mcp.tool()
def memory_save(
    obs_type: str = "note",
    title: str = "",
    content: str = "",
    importance: float = 0.5,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Save observation to cross-session memory."""
    import os

    from gathon.memory import MemoryDB
    db = MemoryDB()
    try:
        obs_id = db.save(
            obs_type=obs_type, title=title, content=content,
            importance=importance,
            project_dir=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()),
            tags=tags,
        )
        return _compressed(
            {"id": obs_id, "title": title, "type": obs_type},
            tool_name="memory_save",
        )
    finally:
        db.close()


@mcp.tool()
def memory_search(
    query: str,
    type_filter: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search cross-session memory via FTS5 (BM25 + fuzzy fallback)."""
    from gathon.memory import MemoryDB
    db = MemoryDB()
    try:
        results = db.search(query, type_filter=type_filter, limit=limit)
        return _compressed({
            "query": query,
            "count": len(results),
            "results": [
                {
                    "id": r.observation.id,
                    "type": r.observation.obs_type,
                    "title": r.observation.title,
                    "score": round(r.score, 3),
                    "snippet": r.snippet,
                    "importance": r.observation.importance,
                    "access_count": r.observation.access_count,
                }
                for r in results
            ],
        }, tool_name="memory_search")
    finally:
        db.close()


@mcp.tool()
def memory_index(
    limit: int = 50,
    type_filter: str | None = None,
) -> dict[str, Any]:
    """List memory observations (compact: id, type, title, importance)."""
    from gathon.memory import MemoryDB
    db = MemoryDB()
    try:
        obs_list = db.index(limit=limit, type_filter=type_filter)
        return _compressed({
            "count": len(obs_list),
            "observations": [
                {
                    "id": o.id,
                    "type": o.obs_type,
                    "title": o.title,
                    "importance": o.importance,
                    "access_count": o.access_count,
                    "created_at": o.created_at,
                }
                for o in obs_list
            ],
        }, tool_name="memory_index")
    finally:
        db.close()


@mcp.tool()
def memory_get(
    obs_id: int,
) -> dict[str, Any]:
    """Get full observation content by ID (increments access count)."""
    from gathon.memory import MemoryDB
    db = MemoryDB()
    try:
        obs = db.get(obs_id)
        if not obs:
            return _compressed({"error": f"Observation {obs_id} not found"}, tool_name="memory_get")
        return _compressed({
            "id": obs.id,
            "type": obs.obs_type,
            "title": obs.title,
            "content": obs.content,
            "importance": obs.importance,
            "access_count": obs.access_count,
            "tags": obs.tags,
            "linked_symbols": obs.linked_symbols,
            "created_at": obs.created_at,
        }, tool_name="memory_get")
    finally:
        db.close()


@mcp.tool()
def memory_delete(
    obs_id: int,
) -> dict[str, Any]:
    """Soft-delete observation (archived, not destroyed)."""
    from gathon.memory import MemoryDB
    db = MemoryDB()
    try:
        deleted = db.delete(obs_id)
        return _compressed({"id": obs_id, "deleted": deleted}, tool_name="memory_delete")
    finally:
        db.close()


@mcp.tool()
def memory_maintain() -> dict[str, Any]:
    """Run memory maintenance: decay stale, promote frequent, dedup."""
    from gathon.memory import MemoryDB
    db = MemoryDB()
    try:
        result = db.maintain()
        return _compressed(result, tool_name="memory_maintain")
    finally:
        db.close()


# === Context Packing (1) ===


@mcp.tool()
def pack_context(
    candidates: list[dict[str, Any]],
    budget_tokens: int = 4000,
    query: str = "",
) -> dict[str, Any]:
    """Knapsack-pack context candidates into token budget."""
    from gathon.packer import auto_pack
    result = auto_pack(candidates, budget=budget_tokens, query=query)
    return _compressed({
        "items_packed": result.items_packed,
        "items_skipped": result.items_skipped,
        "total_tokens": result.total_tokens,
        "budget_used_pct": round(result.budget_used_pct, 1),
        "packed": [
            {"name": c.name, "kind": c.kind, "tokens": c.token_cost}
            for c in result.candidates
        ],
    }, tool_name="pack_context")


# === Prefetch (1) ===


@mcp.tool()
def prefetch_stats() -> dict[str, Any]:
    """Markov prefetcher statistics: transition model, predictions, cache hits."""
    from gathon.prefetch import MarkovPrefetcher
    pf = MarkovPrefetcher()
    return _compressed(pf.stats(), tool_name="prefetch_stats")


# === Breaking Changes (1) ===


@mcp.tool()
def detect_breaking(
    since_ref: str = "HEAD~1",
    file_patterns: list[str] | None = None,
    repo_root: str | None = None,
) -> dict[str, Any]:
    """Detect breaking API changes vs a git ref (removed funcs, changed params, etc.)."""
    store, _ = _get_store(repo_root)
    try:
        from gathon.tools.breaking_changes import detect_breaking_changes
        return _compressed(
            detect_breaking_changes(store, since_ref, file_patterns),
            tool_name="detect_breaking",
        )
    finally:
        store.close()


# === Program Slicer (1) ===


@mcp.tool()
def backward_slice(
    file_path: str,
    variable: str,
    target_line: int,
) -> dict[str, Any]:
    """Backward program slice: minimal statements influencing variable at line (Weiser 1981)."""
    from gathon.tools.slicer import backward_slice as _bs
    return _compressed(_bs(file_path, variable, target_line), tool_name="backward_slice")


# === Prompts (5) ===


@mcp.prompt()
def review_changes(base: str = "HEAD~1") -> list[dict]:
    """Review recent changes with risk analysis."""
    from gathon.prompts import review_changes_prompt
    return review_changes_prompt(base)


@mcp.prompt()
def architecture_map() -> list[dict]:
    """Map codebase architecture from graph structure."""
    from gathon.prompts import architecture_map_prompt
    return architecture_map_prompt()


@mcp.prompt()
def debug_issue(description: str = "") -> list[dict]:
    """Debug an issue using graph traversal."""
    from gathon.prompts import debug_issue_prompt
    return debug_issue_prompt(description)


@mcp.prompt()
def onboard_developer() -> list[dict]:
    """Onboard a new developer to the codebase."""
    from gathon.prompts import onboard_developer_prompt
    return onboard_developer_prompt()


@mcp.prompt()
def pre_merge_check(base: str = "HEAD~1") -> list[dict]:
    """Pre-merge safety check."""
    from gathon.prompts import pre_merge_check_prompt
    return pre_merge_check_prompt(base)


# === Server Entry Point ===


def run(
    repo_root: str | None = None,
    transport: str = "stdio",
) -> None:
    """Start gathon MCP server."""
    global _default_repo_root
    _default_repo_root = repo_root
    mcp.run(transport=transport)
