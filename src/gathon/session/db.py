"""Session event database — SQLite-backed event log and snapshot store."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS session_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 2,
    category TEXT NOT NULL DEFAULT 'general',
    data TEXT NOT NULL DEFAULT '{}',
    source_tool TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_session ON session_events(session_id);
CREATE INDEX IF NOT EXISTS idx_type ON session_events(event_type);
CREATE INDEX IF NOT EXISTS idx_priority ON session_events(priority);
CREATE INDEX IF NOT EXISTS idx_created ON session_events(created_at);

CREATE TABLE IF NOT EXISTS session_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    snapshot TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_snapshot_session ON session_snapshots(session_id);
"""


@dataclass
class SessionEvent:
    event_type: str
    priority: int = 2
    category: str = "general"
    data: dict[str, Any] = field(default_factory=dict)
    source_tool: str = ""
    created_at: str = ""
    id: int = 0
    session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SessionSnapshot:
    session_id: str
    snapshot: str
    size_bytes: int = 0
    created_at: str = ""
    id: int = 0


def _project_hash(project_dir: str) -> str:
    return hashlib.sha256(project_dir.encode()).hexdigest()[:12]


def _default_db_path(project_dir: str | None = None) -> Path:
    base = Path.home() / ".gathon" / "sessions"
    base.mkdir(parents=True, exist_ok=True)
    if project_dir:
        return base / f"{_project_hash(project_dir)}.db"
    return base / "default.db"


class SessionDB:
    """SQLite store for session events and compaction snapshots."""

    def __init__(self, db_path: str | Path | None = None, project_dir: str | None = None) -> None:
        if db_path:
            self._path = Path(db_path)
            self._path.parent.mkdir(parents=True, exist_ok=True)
        else:
            self._path = _default_db_path(project_dir)
        self._conn = sqlite3.connect(str(self._path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()

    def _init_schema(self) -> None:
        for stmt in _SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)
        self._conn.commit()

    @property
    def conn(self) -> sqlite3.Connection:
        return self._conn

    def log_event(
        self,
        session_id: str,
        event_type: str,
        priority: int = 2,
        category: str = "general",
        data: dict[str, Any] | None = None,
        source_tool: str = "",
    ) -> int:
        data_json = json.dumps(data or {})
        cursor = self._conn.execute(
            """INSERT INTO session_events
            (session_id, event_type, priority, category, data, source_tool)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (session_id, event_type, priority, category, data_json, source_tool),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_events(
        self,
        session_id: str,
        since: str | None = None,
        priority_max: int = 3,
    ) -> list[SessionEvent]:
        if since:
            rows = self._conn.execute(
                """SELECT id, session_id, event_type, priority, category,
                    data, source_tool, created_at
                FROM session_events
                WHERE session_id = ? AND priority <= ? AND created_at >= ?
                ORDER BY created_at ASC""",
                (session_id, priority_max, since),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """SELECT id, session_id, event_type, priority, category,
                    data, source_tool, created_at
                FROM session_events
                WHERE session_id = ? AND priority <= ?
                ORDER BY created_at ASC""",
                (session_id, priority_max),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def get_latest_by_type(self, session_id: str, event_type: str) -> SessionEvent | None:
        row = self._conn.execute(
            """SELECT id, session_id, event_type, priority, category,
                data, source_tool, created_at
            FROM session_events
            WHERE session_id = ? AND event_type = ?
            ORDER BY created_at DESC LIMIT 1""",
            (session_id, event_type),
        ).fetchone()
        if not row:
            return None
        return _row_to_event(row)

    def get_event_counts(self, session_id: str) -> dict[str, int]:
        rows = self._conn.execute(
            """SELECT event_type, COUNT(*)
            FROM session_events
            WHERE session_id = ?
            GROUP BY event_type""",
            (session_id,),
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def save_snapshot(self, session_id: str, snapshot_text: str) -> int:
        size_bytes = len(snapshot_text.encode("utf-8"))
        cursor = self._conn.execute(
            """INSERT INTO session_snapshots (session_id, snapshot, size_bytes)
            VALUES (?, ?, ?)""",
            (session_id, snapshot_text, size_bytes),
        )
        self._conn.commit()
        return cursor.lastrowid or 0

    def get_latest_snapshot(self, session_id: str) -> str | None:
        row = self._conn.execute(
            """SELECT snapshot FROM session_snapshots
            WHERE session_id = ?
            ORDER BY created_at DESC LIMIT 1""",
            (session_id,),
        ).fetchone()
        return row[0] if row else None

    def cleanup_old(self, days: int = 7) -> int:
        cursor = self._conn.execute(
            """DELETE FROM session_events
            WHERE created_at < datetime('now', ?)""",
            (f"-{days} days",),
        )
        snap_cursor = self._conn.execute(
            """DELETE FROM session_snapshots
            WHERE created_at < datetime('now', ?)""",
            (f"-{days} days",),
        )
        self._conn.commit()
        return (cursor.rowcount or 0) + (snap_cursor.rowcount or 0)

    def close(self) -> None:
        self._conn.close()


def _row_to_event(row: tuple) -> SessionEvent:
    raw_data = row[5]
    try:
        data = json.loads(raw_data) if raw_data else {}
    except (json.JSONDecodeError, TypeError):
        data = {}
    return SessionEvent(
        id=row[0],
        session_id=row[1],
        event_type=row[2],
        priority=row[3],
        category=row[4],
        data=data,
        source_tool=row[6] or "",
        created_at=row[7] or "",
    )
