"""CLI parser filter telemetry — standalone SQLite at ~/.gathon/cli_parser.db."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cli_parser_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filter_name TEXT NOT NULL,
    command TEXT NOT NULL,
    before_tokens INTEGER NOT NULL,
    after_tokens INTEGER NOT NULL,
    savings_tokens INTEGER NOT NULL,
    savings_pct REAL NOT NULL,
    elapsed_ms REAL NOT NULL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ctp_filter ON cli_parser_telemetry(filter_name);
CREATE INDEX IF NOT EXISTS idx_ctp_created ON cli_parser_telemetry(created_at);
"""


def _default_db_path() -> Path:
    p = Path.home() / ".gathon"
    p.mkdir(parents=True, exist_ok=True)
    return p / "cli_parser.db"


class CtpTelemetryDB:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._path = Path(db_path) if db_path else _default_db_path()
        self._conn = sqlite3.connect(str(self._path))
        for stmt in _SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def log_filter(
        self,
        filter_name: str,
        command: str,
        before_tokens: int,
        after_tokens: int,
        elapsed_ms: float,
    ) -> None:
        savings = before_tokens - after_tokens
        pct = (savings / before_tokens * 100) if before_tokens > 0 else 0.0
        self._conn.execute(
            """INSERT INTO cli_parser_telemetry
            (filter_name, command, before_tokens, after_tokens,
             savings_tokens, savings_pct, elapsed_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (filter_name, command[:200], before_tokens, after_tokens,
             savings, pct, elapsed_ms),
        )
        self._conn.commit()

    def get_summary(self) -> dict[str, Any]:
        row = self._conn.execute(
            """SELECT COUNT(*), COALESCE(SUM(before_tokens), 0),
                COALESCE(SUM(after_tokens), 0),
                COALESCE(SUM(savings_tokens), 0),
                COALESCE(AVG(savings_pct), 0.0),
                COALESCE(AVG(elapsed_ms), 0.0)
            FROM cli_parser_telemetry""",
        ).fetchone()
        return {
            "total_commands": row[0],
            "total_before": row[1],
            "total_after": row[2],
            "total_savings": row[3],
            "avg_savings_pct": round(row[4], 1),
            "avg_elapsed_ms": round(row[5], 1),
        }

    def get_filter_performance(self, filter_name: str) -> float:
        """Return average savings_pct for a filter name.

        Returns 0.0 if no rows exist for this filter or on any error.
        """
        row = self._conn.execute(
            "SELECT AVG(savings_pct) FROM cli_parser_telemetry WHERE filter_name = ?",
            (filter_name,),
        ).fetchone()
        if row is None or row[0] is None:
            return 0.0
        return float(row[0])

    def get_by_filter(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT filter_name, COUNT(*), SUM(before_tokens),
                SUM(after_tokens), SUM(savings_tokens),
                AVG(savings_pct), AVG(elapsed_ms)
            FROM cli_parser_telemetry
            GROUP BY filter_name
            ORDER BY SUM(savings_tokens) DESC""",
        ).fetchall()
        return [
            {
                "filter": r[0], "count": r[1],
                "before": r[2], "after": r[3],
                "savings": r[4], "avg_pct": round(r[5], 1),
                "avg_ms": round(r[6], 1),
            }
            for r in rows
        ]

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT filter_name, command, before_tokens, after_tokens,
                savings_pct, elapsed_ms, created_at
            FROM cli_parser_telemetry
            ORDER BY created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [
            {
                "filter": r[0], "command": r[1],
                "before": r[2], "after": r[3],
                "pct": round(r[4], 1), "ms": round(r[5], 1),
                "at": r[6],
            }
            for r in rows
        ]

    def get_trend(self, days: int = 7) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """SELECT DATE(created_at) as day, COUNT(*),
                SUM(savings_tokens), AVG(savings_pct)
            FROM cli_parser_telemetry
            WHERE created_at >= datetime('now', ?)
            GROUP BY DATE(created_at)
            ORDER BY day""",
            (f"-{days} days",),
        ).fetchall()
        return [
            {
                "date": r[0], "commands": r[1],
                "savings": r[2], "avg_pct": round(r[3], 1),
            }
            for r in rows
        ]
