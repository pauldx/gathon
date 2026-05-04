"""SQLite-backed cross-session memory database."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .models import (
    IMMUNE_TYPES,
    TYPE_TTL,
    Observation,
    ObservationType,
    SearchResult,
)

_DEFAULT_DB_DIR = Path.home() / ".gathon" / "memory"
_DEFAULT_DB_PATH = _DEFAULT_DB_DIR / "memory.db"

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    obs_type TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    importance REAL DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TEXT DEFAULT (datetime('now')),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    archived INTEGER DEFAULT 0,
    project_dir TEXT DEFAULT '',
    linked_symbols TEXT DEFAULT '[]',
    tags TEXT DEFAULT '[]'
);

CREATE VIRTUAL TABLE IF NOT EXISTS obs_fts USING fts5(
    title, content, obs_type, tags,
    content=observations, content_rowid=id,
    tokenize='porter'
);

CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
    INSERT INTO obs_fts(rowid, title, content, obs_type, tags)
    VALUES (new.id, new.title, new.content, new.obs_type, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
    INSERT INTO obs_fts(obs_fts, rowid, title, content, obs_type, tags)
    VALUES ('delete', old.id, old.title, old.content, old.obs_type, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS obs_au AFTER UPDATE ON observations BEGIN
    INSERT INTO obs_fts(obs_fts, rowid, title, content, obs_type, tags)
    VALUES ('delete', old.id, old.title, old.content, old.obs_type, old.tags);
    INSERT INTO obs_fts(rowid, title, content, obs_type, tags)
    VALUES (new.id, new.title, new.content, new.obs_type, new.tags);
END;
"""

# FTS5 special characters that must be escaped in user queries
_FTS5_SPECIAL = re.compile(r'["\*\(\)\-\+\:\^]')


def _escape_fts_query(raw: str) -> str:
    """Escape FTS5 special characters so user input is treated as literal terms."""
    cleaned = _FTS5_SPECIAL.sub(" ", raw)
    terms = cleaned.split()
    if not terms:
        return '""'
    return " ".join(f'"{t}"' for t in terms)


def _row_to_observation(row: sqlite3.Row) -> Observation:
    return Observation(
        id=row["id"],
        obs_type=row["obs_type"],
        title=row["title"],
        content=row["content"],
        importance=row["importance"],
        access_count=row["access_count"],
        last_accessed=row["last_accessed"] or "",
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
        archived=bool(row["archived"]),
        project_dir=row["project_dir"] or "",
        linked_symbols=json.loads(row["linked_symbols"] or "[]"),
        tags=json.loads(row["tags"] or "[]"),
    )


class MemoryDB:
    """Cross-session memory store backed by SQLite with FTS5 search."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            db_path = _DEFAULT_DB_PATH
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA_SQL)

    # -- Context manager ------------------------------------------------

    def __enter__(self) -> MemoryDB:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # -- CRUD -----------------------------------------------------------

    def save(
        self,
        obs_type: str,
        title: str,
        content: str,
        importance: float = 0.5,
        project_dir: str = "",
        linked_symbols: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> int:
        """Save an observation. Upserts on duplicate title+obs_type."""
        linked_symbols = linked_symbols or []
        tags = tags or []
        symbols_json = json.dumps(linked_symbols)
        tags_json = json.dumps(tags)
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        existing = self._conn.execute(
            "SELECT id FROM observations WHERE title = ? AND obs_type = ? AND archived = 0",
            (title, obs_type),
        ).fetchone()

        if existing:
            obs_id = existing["id"]
            self._conn.execute(
                """UPDATE observations
                   SET content = ?, importance = ?, updated_at = ?,
                       project_dir = ?, linked_symbols = ?, tags = ?
                   WHERE id = ?""",
                (content, importance, now, project_dir, symbols_json, tags_json, obs_id),
            )
            self._conn.commit()
            return obs_id

        cursor = self._conn.execute(
            """INSERT INTO observations
               (obs_type, title, content, importance, project_dir,
                linked_symbols, tags, created_at, updated_at, last_accessed)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (obs_type, title, content, importance, project_dir,
             symbols_json, tags_json, now, now, now),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get(self, obs_id: int) -> Observation | None:
        """Fetch an observation by id. Increments access_count and updates last_accessed."""
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        self._conn.execute(
            "UPDATE observations SET access_count = access_count + 1, "
            "last_accessed = ? WHERE id = ?",
            (now, obs_id),
        )
        self._conn.commit()

        row = self._conn.execute(
            "SELECT * FROM observations WHERE id = ?", (obs_id,)
        ).fetchone()
        if row is None:
            return None
        return _row_to_observation(row)

    def get_many(self, ids: list[int]) -> list[Observation]:
        """Fetch multiple observations by id without incrementing access_count."""
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        rows = self._conn.execute(
            f"SELECT * FROM observations WHERE id IN ({placeholders})", ids
        ).fetchall()
        return [_row_to_observation(r) for r in rows]

    def search(
        self,
        query: str,
        type_filter: str | None = None,
        limit: int = 10,
        project_dir: str | None = None,
    ) -> list[SearchResult]:
        """Full-text search using FTS5 BM25 ranking."""
        escaped = _escape_fts_query(query)
        if escaped.strip() in ('', '""'):
            return []

        sql = """
            SELECT o.*, bm25(obs_fts) AS rank,
                   snippet(obs_fts, 1, '>>>', '<<<', '...', 48) AS snip
            FROM obs_fts
            JOIN observations o ON o.id = obs_fts.rowid
            WHERE obs_fts MATCH ?
              AND o.archived = 0
        """
        params: list[Any] = [escaped]

        if type_filter:
            sql += " AND o.obs_type = ?"
            params.append(type_filter)
        if project_dir:
            sql += " AND o.project_dir = ?"
            params.append(project_dir)

        sql += " ORDER BY rank LIMIT ?"
        params.append(limit)

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

        results = []
        for row in rows:
            obs = _row_to_observation(row)
            results.append(SearchResult(
                observation=obs,
                score=abs(row["rank"]),
                snippet=row["snip"] or "",
            ))
        return results

    def index(
        self,
        limit: int = 50,
        type_filter: str | None = None,
    ) -> list[Observation]:
        """Return compact list of observations (content omitted for brevity)."""
        sql = """
            SELECT id, obs_type, title, importance, access_count, created_at
            FROM observations
            WHERE archived = 0
        """
        params: list[Any] = []
        if type_filter:
            sql += " AND obs_type = ?"
            params.append(type_filter)

        sql += " ORDER BY importance DESC, access_count DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            Observation(
                id=r["id"],
                obs_type=r["obs_type"],
                title=r["title"],
                importance=r["importance"],
                access_count=r["access_count"],
                created_at=r["created_at"] or "",
            )
            for r in rows
        ]

    def delete(self, obs_id: int) -> bool:
        """Soft-delete an observation by setting archived=1."""
        cursor = self._conn.execute(
            "UPDATE observations SET archived = 1 WHERE id = ? AND archived = 0",
            (obs_id,),
        )
        self._conn.commit()
        return cursor.rowcount > 0

    def update(
        self,
        obs_id: int,
        content: str | None = None,
        importance: float | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update specific fields of an observation."""
        sets: list[str] = []
        params: list[Any] = []
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        if content is not None:
            sets.append("content = ?")
            params.append(content)
        if importance is not None:
            sets.append("importance = ?")
            params.append(importance)
        if tags is not None:
            sets.append("tags = ?")
            params.append(json.dumps(tags))

        if not sets:
            return False

        sets.append("updated_at = ?")
        params.append(now)
        params.append(obs_id)

        cursor = self._conn.execute(
            f"UPDATE observations SET {', '.join(sets)} WHERE id = ?", params
        )
        self._conn.commit()
        return cursor.rowcount > 0

    # -- Maintenance ----------------------------------------------------

    def decay(self, days_threshold: int | None = None) -> int:
        """Archive observations past their TTL with 0 access. Respects IMMUNE_TYPES."""
        now = datetime.now(UTC)
        archived_count = 0

        immune_set = {str(t) for t in IMMUNE_TYPES}
        rows = self._conn.execute(
            "SELECT id, obs_type, created_at, access_count FROM observations WHERE archived = 0"
        ).fetchall()

        for row in rows:
            if row["obs_type"] in immune_set:
                continue
            if row["access_count"] > 0:
                continue

            ttl_days = days_threshold
            if ttl_days is None:
                ttl_days = TYPE_TTL.get(row["obs_type"], 90)

            created = datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S").replace(
                tzinfo=UTC
            )
            age_days = (now - created).days
            if age_days >= ttl_days:
                self._conn.execute(
                    "UPDATE observations SET archived = 1 WHERE id = ?", (row["id"],)
                )
                archived_count += 1

        self._conn.commit()
        return archived_count

    def promote(self) -> int:
        """Promote frequently-accessed observations to stronger types.

        - note accessed >= 5 times -> convention
        - warning accessed >= 5 times -> guardrail
        """
        count = 0
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        cursor = self._conn.execute(
            """UPDATE observations SET obs_type = ?, updated_at = ?
               WHERE obs_type = ? AND access_count >= 5 AND archived = 0""",
            (ObservationType.CONVENTION, now, ObservationType.NOTE),
        )
        count += cursor.rowcount

        cursor = self._conn.execute(
            """UPDATE observations SET obs_type = ?, updated_at = ?
               WHERE obs_type = ? AND access_count >= 5 AND archived = 0""",
            (ObservationType.GUARDRAIL, now, ObservationType.WARNING),
        )
        count += cursor.rowcount

        self._conn.commit()
        return count

    def dedup(self) -> int:
        """Find observations with same title+type, merge and archive duplicates.

        Keeps the one with higher importance (or lower id on tie), sums access_count.
        """
        rows = self._conn.execute(
            """SELECT title, obs_type, GROUP_CONCAT(id) AS ids
               FROM observations
               WHERE archived = 0
               GROUP BY title, obs_type
               HAVING COUNT(*) > 1"""
        ).fetchall()

        archived_count = 0
        now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

        for row in rows:
            ids = [int(i) for i in row["ids"].split(",")]
            obs_list = self.get_many(ids)
            obs_list.sort(key=lambda o: (-o.importance, o.id))

            keeper = obs_list[0]
            total_access = sum(o.access_count for o in obs_list)

            for dup in obs_list[1:]:
                self._conn.execute(
                    "UPDATE observations SET archived = 1 WHERE id = ?", (dup.id,)
                )
                archived_count += 1

            self._conn.execute(
                "UPDATE observations SET access_count = ?, updated_at = ? WHERE id = ?",
                (total_access, now, keeper.id),
            )

        self._conn.commit()
        return archived_count

    def maintain(self) -> dict[str, int]:
        """Run all maintenance tasks: decay, promote, dedup."""
        decayed = self.decay()
        promoted = self.promote()
        deduped = self.dedup()
        return {"decayed": decayed, "promoted": promoted, "deduped": deduped}

    def stats(self) -> dict[str, Any]:
        """Return summary statistics."""
        total = self._conn.execute(
            "SELECT COUNT(*) AS c FROM observations WHERE archived = 0"
        ).fetchone()["c"]

        archived = self._conn.execute(
            "SELECT COUNT(*) AS c FROM observations WHERE archived = 1"
        ).fetchone()["c"]

        by_type_rows = self._conn.execute(
            """SELECT obs_type, COUNT(*) AS c FROM observations
               WHERE archived = 0 GROUP BY obs_type"""
        ).fetchall()
        by_type = {r["obs_type"]: r["c"] for r in by_type_rows}

        avg_row = self._conn.execute(
            "SELECT AVG(importance) AS avg_imp FROM observations WHERE archived = 0"
        ).fetchone()
        avg_importance = round(avg_row["avg_imp"] or 0.0, 3)

        oldest_row = self._conn.execute(
            "SELECT MIN(created_at) AS oldest FROM observations WHERE archived = 0"
        ).fetchone()
        newest_row = self._conn.execute(
            "SELECT MAX(created_at) AS newest FROM observations WHERE archived = 0"
        ).fetchone()

        return {
            "total": total,
            "by_type": by_type,
            "archived": archived,
            "avg_importance": avg_importance,
            "oldest": oldest_row["oldest"] or "",
            "newest": newest_row["newest"] or "",
        }

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
