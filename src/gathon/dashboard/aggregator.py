"""Multi-DB aggregator — queries all telemetry sources and builds DashboardData."""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gathon.dashboard.coach import generate_coach_data
from gathon.dashboard.models import (
    CodeGraphTabData,
    CoachTabData,
    CtpTabData,
    DashboardData,
    MemoryTabData,
    MultimodalTabData,
    OverviewData,
    QualityTabData,
    WasteTabData,
)
from gathon.dashboard.pricing import tokens_to_cost_usd
from gathon.dashboard.quality import score_quality
from gathon.dashboard.waste import run_all_detectors

MULTIMODAL_PIPELINES = frozenset({
    "gathon_doc",
    "gathon_pdf",
    "gathon_office",
    "gathon_image",
    "gathon_video",
    "gathon_url",
})

ALL_FILTER_NAMES = [
    "cargo_filter",
    "cat_filter",
    "cloud_filter",
    "db_filter",
    "docker_filter",
    "dotnet_filter",
    "gh_filter",
    "git_diff",
    "git_log",
    "git_ops",
    "git_status",
    "go_filter",
    "grep_filter",
    "js_filter",
    "kubectl_filter",
    "ls_filter",
    "pytest_filter",
    "python_filter",
    "ruby_filter",
    "system_filter",
    "terraform_filter",
]


def _query_ctp(days: int) -> tuple[CtpTabData, dict[str, Any]]:
    ctp = CtpTabData()
    meta: dict[str, Any] = {
        "avg_savings_pct": 0.0,
        "total_ctp_savings": 0,
        "total_ctp_commands": 0,
        "by_filter": [],
        "ctp_active_this_week": False,
        "ctp_events_last_7d": 0,
    }
    try:
        from gathon.cli_token_parse.telemetry import CtpTelemetryDB

        db = CtpTelemetryDB()
        summary = db.get_summary()
        by_filter = db.get_by_filter()
        trend = db.get_trend(days)
        top_commands = db.get_history(20)
        week_trend = db.get_trend(7)
        db.close()

        ctp = CtpTabData(
            total_commands=summary.get("total_commands", 0),
            total_savings=summary.get("total_savings", 0),
            avg_savings_pct=summary.get("avg_savings_pct", 0.0),
            by_filter=by_filter,
            trend=trend,
            top_commands=top_commands,
        )
        meta = {
            "avg_savings_pct": summary.get("avg_savings_pct", 0.0),
            "total_ctp_savings": summary.get("total_savings", 0),
            "total_ctp_commands": summary.get("total_commands", 0),
            "by_filter": by_filter,
            "ctp_active_this_week": len(week_trend) > 0,
            "ctp_events_last_7d": sum(e.get("commands", 0) for e in week_trend),
        }
    except Exception as exc:
        print(f"Warning: CTP telemetry unavailable — {exc}", file=sys.stderr)
    return ctp, meta


def _query_graph(
    graph_db_path: Path,
    days: int,
) -> tuple[CodeGraphTabData, MultimodalTabData, dict[str, Any]]:
    code_graph = CodeGraphTabData()
    multimodal = MultimodalTabData()
    meta: dict[str, Any] = {
        "graph_avg_pct": 0.0,
        "total_graph_savings": 0,
        "compression_events": 0,
        "mcp_tool_events": 0,
        "days_with_events": 0,
        "nodes_by_pipeline": {},
        "total_nodes": 0,
        "multimodal_nodes": 0,
        "successful_pipeline_runs": 0,
        "total_pipeline_runs": 0,
        "redundant_ingestions": 0,
        "compression_enabled": False,
        "graph_db_empty": True,
        "unified_stats": {},
    }
    if not graph_db_path.exists():
        return code_graph, multimodal, meta

    try:
        conn = sqlite3.connect(str(graph_db_path))
        conn.row_factory = sqlite3.Row

        from gathon.telemetry import TelemetryStats

        ts = TelemetryStats(conn)
        full_stats = ts.get_full_stats(days)
        summary = full_stats["summary"]
        by_tool = full_stats["by_tool"]
        trend = full_stats["trend"]
        disclosure = full_stats["disclosure"]

        # Session-aware MCP tool event count (proxy for "how many times MCP was used")
        mcp_events_row = conn.execute(
            "SELECT COUNT(*) FROM compression_telemetry WHERE event_type IN ('compress','disclosure')"
        ).fetchone()
        mcp_tool_events = mcp_events_row[0] if mcp_events_row else 0

        # Nodes by pipeline
        nodes_rows = conn.execute(
            "SELECT pipeline, COUNT(*) AS cnt FROM nodes GROUP BY pipeline"
        ).fetchall()
        nodes_by_pipeline: dict[str, int] = {r[0]: r[1] for r in nodes_rows}
        total_nodes = sum(nodes_by_pipeline.values())
        multimodal_nodes = sum(
            cnt for p, cnt in nodes_by_pipeline.items() if p in MULTIMODAL_PIPELINES
        )

        # Pipeline run summary
        run_rows = conn.execute(
            "SELECT pipeline, COUNT(*) AS cnt, AVG(duration_ms) AS avg_ms FROM pipeline_runs GROUP BY pipeline"
        ).fetchall()
        pipeline_run_counts: dict[str, int] = {r[0]: r[1] for r in run_rows}
        total_runs = sum(r[1] for r in run_rows)
        # All runs are considered "successful" (no error column); use total count
        successful_runs = total_runs

        # Redundant ingestions (same file_hash > 3x in multimodal pipelines)
        multi_pipe_placeholders = ",".join("?" * len(MULTIMODAL_PIPELINES))
        redundant_row = conn.execute(
            f"""SELECT COUNT(*) FROM (
                SELECT file_hash FROM pipeline_runs
                WHERE pipeline IN ({multi_pipe_placeholders})
                GROUP BY file_hash HAVING COUNT(*) > 3
            )""",
            list(MULTIMODAL_PIPELINES),
        ).fetchone()
        redundant_ingestions = redundant_row[0] if redundant_row else 0

        # UnifiedStore for graph stats
        unified_stats: dict[str, Any] = {}
        try:
            from gathon.store import UnifiedStore

            store = UnifiedStore(db_path=graph_db_path)
            unified_stats = store.get_unified_stats()
        except Exception:
            pass

        conn.close()

        # Build multimodal compression breakdown by pipeline
        mm_pipelines = {p: nodes_by_pipeline.get(p, 0) for p in MULTIMODAL_PIPELINES if p in nodes_by_pipeline}
        mm_tool_savings = [t for t in by_tool if t["tool"] in {"ingest_url", "ctx_index", "ctx_fetch_and_index", "run_postprocess"}]

        code_graph = CodeGraphTabData(
            unified_stats=unified_stats,
            compression_summary=summary,
            by_tool=[t for t in by_tool if t["tool"] not in {"ingest_url", "ctx_index", "ctx_fetch_and_index", "run_postprocess"}],
            pipeline_run_summary={"counts": pipeline_run_counts, "total_runs": total_runs},
            disclosure_stats=disclosure,
            trend=trend,
        )
        multimodal = MultimodalTabData(
            nodes_by_pipeline=mm_pipelines,
            compression_by_pipeline=mm_tool_savings,
            pipeline_run_counts={p: pipeline_run_counts.get(p, 0) for p in MULTIMODAL_PIPELINES},
            total_multimodal_nodes=multimodal_nodes,
        )
        meta = {
            "graph_avg_pct": summary.get("avg_savings_pct", 0.0),
            "total_graph_savings": summary.get("total_savings_tokens", 0),
            "compression_events": summary.get("total_events", 0),
            "mcp_tool_events": mcp_tool_events,
            "days_with_events": len(trend),
            "nodes_by_pipeline": nodes_by_pipeline,
            "total_nodes": total_nodes,
            "multimodal_nodes": multimodal_nodes,
            "successful_pipeline_runs": successful_runs,
            "total_pipeline_runs": total_runs,
            "redundant_ingestions": redundant_ingestions,
            "compression_enabled": summary.get("total_events", 0) > 0,
            "graph_db_empty": total_nodes == 0,
            "unified_stats": unified_stats,
        }
    except Exception as exc:
        print(f"Warning: Graph telemetry unavailable — {exc}", file=sys.stderr)
    return code_graph, multimodal, meta


def _query_memory() -> tuple[MemoryTabData, dict[str, Any]]:
    mem = MemoryTabData()
    meta: dict[str, Any] = {
        "memory_total": 0,
        "memory_avg_importance": 0.0,
        "memory_has_observations": False,
        "memory_archive_rate": 0.0,
        "memory_stats": {},
    }
    try:
        from gathon.memory import MemoryDB

        db = MemoryDB()
        stats = db.stats()
        observations = db.index(limit=500)
        db.close()

        total = stats.get("total", 0)
        archived = stats.get("archived", 0)
        archive_rate = archived / max(total + archived, 1)
        avg_imp = stats.get("avg_importance", 0.0)

        # ROI distribution bucketed by importance
        buckets = [
            {"range": "0.0–0.2", "count": 0},
            {"range": "0.2–0.4", "count": 0},
            {"range": "0.4–0.6", "count": 0},
            {"range": "0.6–0.8", "count": 0},
            {"range": "0.8–1.0", "count": 0},
        ]
        for obs in observations:
            imp = getattr(obs, "importance", 0.5)
            idx = min(int(imp * 5), 4)
            buckets[idx]["count"] += 1

        # Rough reuse savings: access_count * avg tokens per memory recall (heuristic ~200 tokens)
        total_accesses = sum(getattr(o, "access_count", 0) for o in observations)
        estimated_reuse_savings = total_accesses * 200

        mem = MemoryTabData(
            total=total,
            by_type=stats.get("by_type", {}),
            archived=archived,
            avg_importance=avg_imp,
            archive_rate_pct=round(archive_rate * 100, 1),
            estimated_reuse_savings=estimated_reuse_savings,
            roi_distribution=buckets,
        )
        meta = {
            "memory_total": total,
            "memory_avg_importance": avg_imp,
            "memory_has_observations": total > 0,
            "memory_archive_rate": archive_rate,
            "memory_stats": stats,
        }
    except Exception as exc:
        print(f"Warning: Memory DB unavailable — {exc}", file=sys.stderr)
    return mem, meta


def _query_sessions(days: int) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "session_event_count": 0,
        "error_events": 0,
        "total_events": 0,
        "sessions_over_100_events": 0,
        "error_rate": 0.0,
        "session_tracking_active": False,
    }
    sessions_dir = Path.home() / ".gathon" / "sessions"
    if not sessions_dir.exists():
        return meta

    total_events = 0
    error_events = 0
    sessions_over_100 = 0

    for db_file in sessions_dir.glob("*.db"):
        try:
            conn = sqlite3.connect(str(db_file))
            # Event type counts within window
            rows = conn.execute(
                """SELECT event_type, COUNT(*) FROM session_events
                WHERE created_at >= datetime('now', ?)
                GROUP BY event_type""",
                (f"-{days} days",),
            ).fetchall()
            for row in rows:
                count = row[1]
                total_events += count
                if row[0] == "error":
                    error_events += count

            # Sessions with > 100 events
            bloated = conn.execute(
                """SELECT COUNT(*) FROM (
                    SELECT session_id FROM session_events
                    GROUP BY session_id HAVING COUNT(*) > 100
                )"""
            ).fetchone()
            if bloated:
                sessions_over_100 += bloated[0]
            conn.close()
        except Exception:
            pass

    error_rate = error_events / max(total_events, 1)
    meta = {
        "session_event_count": total_events,
        "error_events": error_events,
        "total_events": total_events,
        "sessions_over_100_events": sessions_over_100,
        "error_rate": error_rate,
        "session_tracking_active": total_events > 0,
    }
    return meta


def aggregate(days: int, repo_path: Path) -> DashboardData:
    graph_db_path = repo_path / ".gathon" / "graph.db"

    ctp_tab, ctp_meta = _query_ctp(days)
    graph_tab, mm_tab, graph_meta = _query_graph(graph_db_path, days)
    mem_tab, mem_meta = _query_memory()
    session_meta = _query_sessions(days)

    # Merge trend (CTP + graph)
    merged: dict[str, int] = defaultdict(int)
    for entry in ctp_tab.trend:
        merged[entry["date"]] += entry.get("savings", 0)
    for entry in graph_tab.trend:
        merged[entry["date"]] += entry.get("savings_tokens", 0)
    trend = [{"date": d, "savings": s} for d, s in sorted(merged.items())]

    total_savings = ctp_meta["total_ctp_savings"] + graph_meta["total_graph_savings"]
    estimated_cost = tokens_to_cost_usd(total_savings)

    avg_savings = 0.0
    if ctp_meta["avg_savings_pct"] > 0 or graph_meta["graph_avg_pct"] > 0:
        parts = [p for p in [ctp_meta["avg_savings_pct"], graph_meta["graph_avg_pct"]] if p > 0]
        avg_savings = sum(parts) / len(parts)

    overview = OverviewData(
        total_savings_tokens=total_savings,
        estimated_cost_usd=round(estimated_cost, 4),
        ctp_savings=ctp_meta["total_ctp_savings"],
        graph_savings=graph_meta["total_graph_savings"],
        multimodal_savings=0,
        memory_savings=mem_tab.estimated_reuse_savings,
        session_event_count=session_meta["session_event_count"],
        days=days,
        trend=trend,
    )

    # Quality inputs
    quality_inputs = {
        "ctp_avg_pct": ctp_meta["avg_savings_pct"],
        "graph_avg_pct": graph_meta["graph_avg_pct"],
        "total_ctp_commands": ctp_meta["total_ctp_commands"],
        "total_days": days,
        "days_with_events": graph_meta["days_with_events"],
        "error_events": session_meta["error_events"],
        "total_events": session_meta["total_events"],
        "successful_pipeline_runs": graph_meta["successful_pipeline_runs"],
        "total_pipeline_runs": graph_meta["total_pipeline_runs"],
        "multimodal_nodes": graph_meta["multimodal_nodes"],
        "total_nodes": graph_meta["total_nodes"],
        "memory_total": mem_meta["memory_total"],
        "memory_avg_importance": mem_meta["memory_avg_importance"],
    }
    quality_tab = score_quality(quality_inputs)

    # Waste inputs
    session_stats = {
        "sessions_over_100_events": session_meta["sessions_over_100_events"],
        "error_rate": session_meta["error_rate"],
        "total_events": session_meta["total_events"],
    }
    waste_stats = {
        "by_filter": ctp_meta["by_filter"],
        "session_stats": session_stats,
        "compression_events": graph_meta["compression_events"],
        "mcp_tool_events": graph_meta["mcp_tool_events"],
        "all_filter_names": ALL_FILTER_NAMES,
        "memory_stats": mem_meta["memory_stats"],
        "redundant_ingestions": graph_meta["redundant_ingestions"],
    }
    waste_tab = run_all_detectors(waste_stats)

    # Coach inputs
    coach_stats = {
        "ctp_active_this_week": ctp_meta["ctp_active_this_week"],
        "memory_has_observations": mem_meta["memory_has_observations"],
        "compression_enabled": graph_meta["compression_enabled"],
        "session_tracking_active": session_meta["session_tracking_active"],
        "ctp_events_last_7d": ctp_meta["ctp_events_last_7d"],
        "avg_savings_pct": avg_savings,
        "memory_archive_rate": mem_meta["memory_archive_rate"],
        "graph_db_empty": graph_meta["graph_db_empty"],
        "multimodal_nodes": graph_meta["multimodal_nodes"],
        "total_ctp_savings": ctp_meta["total_ctp_savings"],
        "total_graph_savings": graph_meta["total_graph_savings"],
        "memory_total": mem_meta["memory_total"],
    }
    coach_tab = generate_coach_data(coach_stats)

    return DashboardData(
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        days=days,
        repo_path=str(repo_path),
        overview=overview,
        ctp=ctp_tab,
        code_graph=graph_tab,
        multimodal=mm_tab,
        memory=mem_tab,
        quality=quality_tab,
        waste=waste_tab,
        coach=coach_tab,
    )
