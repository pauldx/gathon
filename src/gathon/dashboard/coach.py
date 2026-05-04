"""Health scorer and recommendation engine for the Coach tab."""

from __future__ import annotations

from gathon.dashboard.models import CoachPattern, CoachTabData


def _score_to_grade(score: int) -> str:
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 55:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def generate_coach_data(stats: dict) -> CoachTabData:
    """
    stats keys:
      ctp_active_this_week (bool), memory_has_observations (bool),
      compression_enabled (bool), session_tracking_active (bool),
      ctp_events_last_7d (int), avg_savings_pct (float),
      memory_archive_rate (float), graph_db_empty (bool),
      multimodal_nodes (int), total_ctp_savings (int),
      total_graph_savings (int), memory_total (int)
    """
    score = 70
    good: list[CoachPattern] = []
    bad: list[CoachPattern] = []

    if stats.get("ctp_active_this_week"):
        score += 5
        good.append(CoachPattern(
            "CLI Token Parse active",
            "CTP filter is intercepting and compressing Bash command output",
            "good",
        ))

    if stats.get("memory_has_observations"):
        score += 5
        good.append(CoachPattern(
            "Memory in use",
            f"{stats.get('memory_total', 0)} observations building cross-session knowledge",
            "good",
        ))

    if stats.get("compression_enabled"):
        score += 5
        good.append(CoachPattern(
            "MCP compression on",
            "Graph tool responses are being compressed before reaching the model",
            "good",
        ))

    if stats.get("session_tracking_active"):
        score += 5
        good.append(CoachPattern(
            "Session tracking active",
            "Session events are being logged for analysis",
            "good",
        ))

    if not stats.get("ctp_active_this_week") and stats.get("ctp_events_last_7d", 0) == 0:
        score -= 5
        bad.append(CoachPattern(
            "CTP not running",
            "No CLI filter events in last 7 days — hook may not be installed. Run `gathon ctp-init`",
            "bad",
        ))

    avg_pct = stats.get("avg_savings_pct", 0.0)
    total_savings = stats.get("total_ctp_savings", 0) + stats.get("total_graph_savings", 0)
    if avg_pct < 20.0 and total_savings > 0:
        score -= 5
        bad.append(CoachPattern(
            f"Low savings rate ({avg_pct:.1f}%)",
            "Average token savings below 20% — filters may need tuning or compression level too low",
            "bad",
        ))

    mem_archive = stats.get("memory_archive_rate", 0.0)
    if mem_archive > 0.80 and stats.get("memory_total", 0) > 10:
        score -= 5
        bad.append(CoachPattern(
            "High memory archive rate",
            "Over 80% of observations archived — memories saved but rarely reused",
            "bad",
        ))

    if stats.get("graph_db_empty"):
        score -= 5
        bad.append(CoachPattern(
            "No graph built",
            "Run `gathon build` to index codebase and enable graph-based compression",
            "bad",
        ))

    if stats.get("multimodal_nodes", 0) == 0:
        score -= 3
        bad.append(CoachPattern(
            "No multimodal content",
            "Ingest docs/PDFs/URLs to extend knowledge graph beyond code",
            "bad",
        ))

    score = max(0, min(100, score))
    grade = _score_to_grade(score)

    snapshot = {
        "total_ctp_savings": stats.get("total_ctp_savings", 0),
        "total_graph_savings": stats.get("total_graph_savings", 0),
        "memory_observations": stats.get("memory_total", 0),
        "active_modules": sum([
            bool(stats.get("ctp_active_this_week")),
            bool(stats.get("memory_has_observations")),
            bool(stats.get("compression_enabled")),
            bool(stats.get("session_tracking_active")),
        ]),
    }
    return CoachTabData(
        health_score=score,
        grade=grade,
        patterns_good=good,
        patterns_bad=bad,
        snapshot=snapshot,
    )
