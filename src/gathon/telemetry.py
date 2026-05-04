"""Compression telemetry: log and query token savings events.

Logs every compression event and detail_level choice to SQLite.
Query interface for stats aggregation used by MCP tool + CLI.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from gathon.tokens import estimate_tokens


class TelemetryLogger:
    """Log compression and disclosure events to SQLite."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def log_compression(
        self,
        tool_name: str,
        before_data: dict[str, Any],
        after_data: dict[str, Any],
        intensity: str,
    ) -> None:
        before_tok = estimate_tokens(before_data)
        after_tok = estimate_tokens(after_data)
        savings = before_tok - after_tok
        pct = (savings / before_tok * 100) if before_tok > 0 else 0.0

        self._conn.execute(
            """INSERT INTO compression_telemetry
            (tool_name, event_type, before_tokens, after_tokens,
             savings_tokens, savings_pct, intensity)
            VALUES (?, 'compress', ?, ?, ?, ?, ?)""",
            (tool_name, before_tok, after_tok, savings, pct, intensity),
        )
        self._conn.commit()

    def log_disclosure(
        self,
        tool_name: str,
        detail_level: str,
        result_tokens: int,
    ) -> None:
        self._conn.execute(
            """INSERT INTO compression_telemetry
            (tool_name, event_type, before_tokens, after_tokens,
             savings_tokens, savings_pct, intensity, detail_level)
            VALUES (?, 'disclosure', 0, ?, 0, 0.0, '', ?)""",
            (tool_name, result_tokens, detail_level),
        )
        self._conn.commit()


class TelemetryStats:
    """Query compression telemetry for aggregated stats."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get_compression_summary(self) -> dict[str, Any]:
        row = self._conn.execute(
            """SELECT
                COUNT(*) as total_events,
                COALESCE(SUM(before_tokens), 0) as total_before,
                COALESCE(SUM(after_tokens), 0) as total_after,
                COALESCE(SUM(savings_tokens), 0) as total_savings,
                COALESCE(AVG(savings_pct), 0.0) as avg_savings_pct
            FROM compression_telemetry
            WHERE event_type = 'compress'""",
        ).fetchone()
        return {
            "total_events": row[0],
            "total_before_tokens": row[1],
            "total_after_tokens": row[2],
            "total_savings_tokens": row[3],
            "avg_savings_pct": round(row[4], 1),
        }

    def get_per_tool_breakdown(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT
                tool_name,
                COUNT(*) as events,
                SUM(before_tokens) as before_total,
                SUM(after_tokens) as after_total,
                SUM(savings_tokens) as savings_total,
                AVG(savings_pct) as avg_pct
            FROM compression_telemetry
            WHERE event_type = 'compress'
            GROUP BY tool_name
            ORDER BY savings_total DESC""",
        ).fetchall()
        return [
            {
                "tool": r[0],
                "events": r[1],
                "before_tokens": r[2],
                "after_tokens": r[3],
                "savings_tokens": r[4],
                "avg_savings_pct": round(r[5], 1),
            }
            for r in rows
        ]

    def get_per_intensity_breakdown(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT
                intensity,
                COUNT(*) as events,
                SUM(savings_tokens) as savings_total,
                AVG(savings_pct) as avg_pct
            FROM compression_telemetry
            WHERE event_type = 'compress'
            GROUP BY intensity
            ORDER BY savings_total DESC""",
        ).fetchall()
        return [
            {
                "intensity": r[0],
                "events": r[1],
                "savings_tokens": r[2],
                "avg_savings_pct": round(r[3], 1),
            }
            for r in rows
        ]

    def get_disclosure_stats(self) -> dict[str, Any]:
        rows = self._conn.execute(
            """SELECT
                detail_level,
                COUNT(*) as events,
                SUM(after_tokens) as total_tokens
            FROM compression_telemetry
            WHERE event_type = 'disclosure'
            GROUP BY detail_level""",
        ).fetchall()

        by_level = {
            r[0]: {"events": r[1], "total_tokens": r[2]}
            for r in rows
        }

        index_count = by_level.get("index", {}).get("events", 0)
        full_count = by_level.get("full", {}).get("events", 0)
        total = index_count + full_count
        upgrade_rate = (
            (full_count / total * 100) if total > 0 else 0.0
        )

        return {
            "by_level": by_level,
            "total_queries": total,
            "index_queries": index_count,
            "full_queries": full_count,
            "upgrade_rate_pct": round(upgrade_rate, 1),
        }

    def get_trend(self, days: int = 7) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT
                DATE(created_at) as day,
                COUNT(*) as events,
                SUM(savings_tokens) as savings,
                AVG(savings_pct) as avg_pct
            FROM compression_telemetry
            WHERE event_type = 'compress'
              AND created_at >= datetime('now', ?)
            GROUP BY DATE(created_at)
            ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
        return [
            {
                "date": r[0],
                "events": r[1],
                "savings_tokens": r[2],
                "avg_savings_pct": round(r[3], 1),
            }
            for r in rows
        ]

    def get_full_stats(self, days: int = 7) -> dict[str, Any]:
        return {
            "summary": self.get_compression_summary(),
            "by_tool": self.get_per_tool_breakdown(),
            "by_intensity": self.get_per_intensity_breakdown(),
            "disclosure": self.get_disclosure_stats(),
            "trend": self.get_trend(days),
        }
