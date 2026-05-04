"""7 gathon-native waste detectors."""

from __future__ import annotations

from gathon.dashboard.models import WasteFinding, WasteTabData

MULTIMODAL_PIPELINES = frozenset({
    "gathon_doc",
    "gathon_pdf",
    "gathon_office",
    "gathon_image",
    "gathon_video",
    "gathon_url",
})


def detect_empty_ctp_runs(by_filter: list[dict]) -> list[WasteFinding]:
    findings = []
    for f in by_filter:
        if f.get("count", 0) >= 5 and f.get("avg_pct", 100.0) < 5.0:
            findings.append(
                WasteFinding(
                    waste_type="empty_ctp_filter",
                    severity="low",
                    description=(
                        f"Filter '{f['filter']}' fired {f['count']}× "
                        f"but saves only {f['avg_pct']:.1f}% on average"
                    ),
                    monthly_waste_tokens=0,
                    recommendation=(
                        f"Review filter '{f['filter']}' — "
                        "it matches commands but compresses little"
                    ),
                    evidence={
                        "filter": f["filter"],
                        "count": f["count"],
                        "avg_pct": f["avg_pct"],
                    },
                )
            )
    return findings


def detect_session_history_bloat(session_stats: dict) -> list[WasteFinding]:
    bloated = session_stats.get("sessions_over_100_events", 0)
    if bloated >= 2:
        return [
            WasteFinding(
                waste_type="session_history_bloat",
                severity="medium",
                description=f"{bloated} session(s) have >100 events without compaction",
                monthly_waste_tokens=bloated * 50_000,
                recommendation="Run `gathon session --snapshot` to compact long sessions",
                evidence={"bloated_sessions": bloated},
            )
        ]
    return []


def detect_error_churn(session_stats: dict) -> list[WasteFinding]:
    error_rate = session_stats.get("error_rate", 0.0)
    total = session_stats.get("total_events", 0)
    if error_rate > 0.30 and total > 20:
        return [
            WasteFinding(
                waste_type="error_churn",
                severity="medium",
                description=(
                    f"High error rate: {error_rate:.0%} of session events are errors"
                ),
                monthly_waste_tokens=int(total * error_rate * 200),
                recommendation=(
                    "Check `gathon session` for recurring errors — "
                    "retried failures burn tokens"
                ),
                evidence={
                    "error_rate": round(error_rate, 3),
                    "total_events": total,
                },
            )
        ]
    return []


def detect_compression_waste(
    compression_events: int,
    mcp_tool_events: int,
) -> list[WasteFinding]:
    if mcp_tool_events < 10:
        return []
    ratio = compression_events / mcp_tool_events
    if ratio < 0.1:
        return [
            WasteFinding(
                waste_type="compression_disabled",
                severity="medium",
                description=(
                    f"Only {compression_events} compression events vs "
                    f"{mcp_tool_events} MCP tool calls ({ratio:.0%})"
                ),
                monthly_waste_tokens=mcp_tool_events * 800,
                recommendation=(
                    "Start gathon with `--compress full` to enable MCP response compression"
                ),
                evidence={
                    "compression_events": compression_events,
                    "mcp_tool_events": mcp_tool_events,
                },
            )
        ]
    return []


def detect_stale_filters(
    by_filter: list[dict],
    all_filter_names: list[str],
) -> list[WasteFinding]:
    active = {f["filter"] for f in by_filter}
    stale = [n for n in all_filter_names if n not in active]
    if len(stale) >= 3:
        examples = stale[:5]
        suffix = "..." if len(stale) > 5 else ""
        return [
            WasteFinding(
                waste_type="stale_filters",
                severity="low",
                description=(
                    f"{len(stale)} CTP filters registered but never triggered: "
                    f"{', '.join(examples)}{suffix}"
                ),
                monthly_waste_tokens=0,
                recommendation=(
                    "These filters load at startup but never match — "
                    "review filter patterns if commands are being missed"
                ),
                evidence={"stale_count": len(stale), "examples": examples},
            )
        ]
    return []


def detect_memory_abandonment(memory_stats: dict) -> list[WasteFinding]:
    total = memory_stats.get("total", 0)
    if total < 5:
        return []
    avg_imp = memory_stats.get("avg_importance", 1.0)
    if avg_imp < 0.3 and total >= 10:
        return [
            WasteFinding(
                waste_type="memory_abandonment",
                severity="medium",
                description=(
                    f"{total} observations with avg importance {avg_imp:.2f} — "
                    "memories saved but low utility score"
                ),
                monthly_waste_tokens=0,
                recommendation=(
                    "Run `gathon memory --maintain` to prune low-value observations; "
                    "use `memory_search` more often to build access counts"
                ),
                evidence={"total": total, "avg_importance": round(avg_imp, 3)},
            )
        ]
    return []


def detect_multimodal_redundancy(redundant_ingestions: int) -> list[WasteFinding]:
    if redundant_ingestions >= 3:
        return [
            WasteFinding(
                waste_type="multimodal_redundancy",
                severity="low",
                description=(
                    f"{redundant_ingestions} files re-ingested with duplicate content hashes"
                ),
                monthly_waste_tokens=redundant_ingestions * 2_000,
                recommendation=(
                    "Use incremental build to skip unchanged files: `gathon build`"
                ),
                evidence={"redundant_ingestions": redundant_ingestions},
            )
        ]
    return []


def run_all_detectors(stats: dict) -> WasteTabData:
    """
    stats keys:
      by_filter, session_stats, compression_events, mcp_tool_events,
      all_filter_names, memory_stats, redundant_ingestions
    """
    all_findings: list[WasteFinding] = []
    all_findings += detect_empty_ctp_runs(stats.get("by_filter", []))
    all_findings += detect_session_history_bloat(stats.get("session_stats", {}))
    all_findings += detect_error_churn(stats.get("session_stats", {}))
    all_findings += detect_compression_waste(
        stats.get("compression_events", 0),
        stats.get("mcp_tool_events", 0),
    )
    all_findings += detect_stale_filters(
        stats.get("by_filter", []),
        stats.get("all_filter_names", []),
    )
    all_findings += detect_memory_abandonment(stats.get("memory_stats", {}))
    all_findings += detect_multimodal_redundancy(stats.get("redundant_ingestions", 0))

    _order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    all_findings.sort(key=lambda f: _order.get(f.severity, 99))

    counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in all_findings:
        counts[f.severity] = counts.get(f.severity, 0) + 1
    return WasteTabData(findings=all_findings, severity_counts=counts)
