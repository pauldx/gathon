"""7-signal quality scorer adapted to gathon's telemetry."""

from __future__ import annotations

from gathon.dashboard.models import QualityTabData, SignalResult


def _score_to_grade(score: float) -> tuple[str, str]:
    if score >= 90:
        return "S", "Excellent"
    if score >= 80:
        return "A", "Good"
    if score >= 70:
        return "B", "Fair"
    if score >= 55:
        return "C", "Needs Work"
    if score >= 40:
        return "D", "Poor"
    return "F", "Critical"


def score_token_savings_rate(ctp_avg_pct: float, graph_avg_pct: float) -> SignalResult:
    divisor = (1 if ctp_avg_pct > 0 else 0) + (1 if graph_avg_pct > 0 else 0)
    combined = (ctp_avg_pct + graph_avg_pct) / max(divisor, 1)
    raw_score = min(100.0, combined * 2.0)  # 50% savings → 100
    if raw_score >= 80:
        rec = ""
    elif raw_score < 40:
        rec = "Enable compression with `gathon serve --compress full`"
    else:
        rec = "Run `gathon ctp-init` to activate CLI token parse"
    return SignalResult(
        "Token Savings Rate",
        0.20,
        raw_score,
        f"Avg compression {combined:.1f}% across CTP and graph tools",
        rec,
    )


def score_ctp_coverage(total_ctp_commands: int, total_days: int) -> SignalResult:
    daily_rate = total_ctp_commands / max(total_days, 1)
    if daily_rate >= 20:
        raw_score = 100.0
    elif daily_rate >= 10:
        raw_score = 80.0
    elif daily_rate >= 5:
        raw_score = 60.0
    elif daily_rate >= 1:
        raw_score = 40.0
    else:
        raw_score = 10.0
    rec = "" if raw_score >= 80 else "Run `gathon ctp-init` to install CLI token parse hook"
    return SignalResult(
        "CTP Coverage",
        0.16,
        raw_score,
        f"{daily_rate:.1f} CLI commands filtered/day",
        rec,
    )


def score_compression_consistency(days_with_events: int, total_days: int) -> SignalResult:
    ratio = days_with_events / max(total_days, 1)
    raw_score = min(100.0, ratio * 120.0)
    rec = "" if raw_score >= 70 else "Start gathon MCP server to enable graph compression"
    return SignalResult(
        "Compression Consistency",
        0.16,
        raw_score,
        f"Compression active {days_with_events}/{total_days} days",
        rec,
    )


def score_memory_utilization(total_obs: int, avg_importance: float) -> SignalResult:
    if total_obs >= 50 and avg_importance >= 0.5:
        raw_score = 100.0
    elif total_obs >= 20 and avg_importance >= 0.4:
        raw_score = 75.0
    elif total_obs >= 10:
        raw_score = 50.0
    elif total_obs >= 1:
        raw_score = 30.0
    else:
        raw_score = 0.0
    if raw_score >= 75:
        rec = ""
    elif total_obs < 5:
        rec = "Use `memory_save` MCP tool to build cross-session knowledge base"
    else:
        rec = "Run `gathon memory --maintain` to prune stale observations"
    return SignalResult(
        "Memory Utilization",
        0.16,
        raw_score,
        f"{total_obs} observations, avg importance {avg_importance:.2f}",
        rec,
    )


def score_error_rate(error_events: int, total_events: int) -> SignalResult:
    if total_events == 0:
        return SignalResult(
            "Error Rate",
            0.12,
            50.0,
            "No session data",
            "Run gathon with MCP server to collect session events",
        )
    rate = error_events / total_events
    if rate < 0.05:
        raw_score = 100.0
    elif rate < 0.15:
        raw_score = 70.0
    elif rate < 0.30:
        raw_score = 40.0
    else:
        raw_score = 15.0
    rec = "" if raw_score >= 70 else f"High error rate ({rate:.0%}) — check session logs with `gathon session`"
    return SignalResult(
        "Error Rate",
        0.12,
        raw_score,
        f"{error_events} errors / {total_events} events ({rate:.0%})",
        rec,
    )


def score_graph_build_health(successful_runs: int, total_runs: int) -> SignalResult:
    if total_runs == 0:
        return SignalResult(
            "Graph Build Health",
            0.10,
            50.0,
            "No pipeline runs yet",
            "Run `gathon build` to index codebase",
        )
    ratio = successful_runs / total_runs
    raw_score = min(100.0, ratio * 110.0)
    rec = "" if raw_score >= 80 else "Build failures detected — run `gathon build` to diagnose"
    return SignalResult(
        "Graph Build Health",
        0.10,
        raw_score,
        f"{successful_runs}/{total_runs} pipeline runs succeeded",
        rec,
    )


def score_multimodal_adoption(multimodal_nodes: int, total_nodes: int) -> SignalResult:
    if total_nodes == 0:
        return SignalResult(
            "Multimodal Adoption",
            0.10,
            30.0,
            "No graph built yet",
            "Run `gathon build` first",
        )
    ratio = multimodal_nodes / total_nodes
    if ratio >= 0.30:
        raw_score = 100.0
    elif ratio >= 0.10:
        raw_score = 80.0
    elif ratio >= 0.01:
        raw_score = 60.0
    else:
        raw_score = 30.0
    rec = "" if raw_score >= 80 else "Ingest docs/PDFs with `gathon build` or `ingest_url` MCP tool"
    return SignalResult(
        "Multimodal Adoption",
        0.10,
        raw_score,
        f"{multimodal_nodes} multimodal nodes ({ratio:.0%} of {total_nodes} total)",
        rec,
    )


def score_quality(inputs: dict) -> QualityTabData:
    """
    Expected inputs keys:
      ctp_avg_pct, graph_avg_pct, total_ctp_commands, total_days,
      days_with_events, error_events, total_events,
      successful_pipeline_runs, total_pipeline_runs,
      multimodal_nodes, total_nodes, memory_total, memory_avg_importance
    """
    signals = [
        score_token_savings_rate(
            inputs.get("ctp_avg_pct", 0.0),
            inputs.get("graph_avg_pct", 0.0),
        ),
        score_ctp_coverage(
            inputs.get("total_ctp_commands", 0),
            inputs.get("total_days", 7),
        ),
        score_compression_consistency(
            inputs.get("days_with_events", 0),
            inputs.get("total_days", 7),
        ),
        score_memory_utilization(
            inputs.get("memory_total", 0),
            inputs.get("memory_avg_importance", 0.0),
        ),
        score_error_rate(
            inputs.get("error_events", 0),
            inputs.get("total_events", 0),
        ),
        score_graph_build_health(
            inputs.get("successful_pipeline_runs", 0),
            inputs.get("total_pipeline_runs", 0),
        ),
        score_multimodal_adoption(
            inputs.get("multimodal_nodes", 0),
            inputs.get("total_nodes", 0),
        ),
    ]
    total = sum(s.score * s.weight for s in signals)
    grade, band = _score_to_grade(total)
    recs = [s.recommendation for s in signals if s.recommendation]
    return QualityTabData(
        score=round(total, 1),
        grade=grade,
        band=band,
        signals=signals,
        recommendations=recs,
    )
