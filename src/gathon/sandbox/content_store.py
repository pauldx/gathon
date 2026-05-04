"""ContentStore — FTS5-backed knowledge base for sandbox output indexing."""

from __future__ import annotations

import difflib
import json
import logging
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from gathon.sandbox.chunker import Chunk, chunk_json, chunk_markdown, chunk_plaintext

logger = logging.getLogger(__name__)

_DB_DIR = Path.home() / ".gathon"
_DB_PATH = _DB_DIR / "sandbox_store.db"

# Cap search output at 40KB
_SEARCH_OUTPUT_CAP = 40 * 1024

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    source_type TEXT DEFAULT 'text',
    chunk_count INTEGER DEFAULT 0,
    total_bytes INTEGER DEFAULT 0,
    indexed_at TEXT DEFAULT (datetime('now'))
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    source_id UNINDEXED,
    title,
    content,
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_trigram USING fts5(
    source_id UNINDEXED,
    title,
    content,
    tokenize='trigram'
);
"""


@dataclass
class SearchResult:
    source_label: str
    title: str
    snippet: str
    score: float
    source_id: int


class ContentStore:
    """SQLite FTS5 content store for indexing and searching sandbox output."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            _DB_DIR.mkdir(parents=True, exist_ok=True)
            db_path = _DB_PATH
        else:
            db_path = Path(db_path)
            db_path.parent.mkdir(parents=True, exist_ok=True)

        self._db_path = db_path
        self._conn = sqlite3.connect(str(db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_schema()
        self._vocab_cache: list[str] | None = None

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        for stmt in _SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    self._conn.execute(stmt)
                except sqlite3.OperationalError:
                    # FTS5 tables may already exist
                    pass
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> ContentStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def index(self, label: str, content: str, source_type: str = "text") -> int:
        """Chunk and index content, return source_id."""
        if not content.strip():
            return -1

        chunks = self._auto_chunk(content, source_type)
        if not chunks:
            chunks = [Chunk("content", content)]

        source_id = self._create_source(label, source_type, len(chunks), len(content))
        self._insert_chunks(source_id, chunks)
        self._vocab_cache = None
        return source_id

    def index_json(self, label: str, data: dict | list) -> int:
        """Index structured JSON data with key-path titles."""
        serialized = json.dumps(data, default=str, ensure_ascii=False)
        chunks = chunk_json(data)
        if not chunks:
            chunks = [Chunk("root", serialized)]

        source_id = self._create_source(label, "json", len(chunks), len(serialized))
        self._insert_chunks(source_id, chunks)
        self._vocab_cache = None
        return source_id

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        """3-tier fallback search: porter FTS5 -> trigram FTS5 -> fuzzy."""
        if not query.strip():
            return []

        # Tier 1: Porter stemming FTS5
        results = self._fts5_search("chunks", query, limit)
        if results:
            return self._cap_results(results)

        # Tier 2: Trigram FTS5 (partial match)
        results = self._fts5_search("chunks_trigram", query, limit)
        if results:
            return self._cap_results(results)

        # Tier 3: Fuzzy Levenshtein via difflib
        results = self._fuzzy_search(query, limit)
        return self._cap_results(results)

    def fetch_and_index(self, url: str, label: str | None = None) -> int:
        """Fetch URL content, convert HTML to text, chunk, and index."""
        if label is None:
            label = url

        try:
            req = Request(url, headers={"User-Agent": "gathon-sandbox/0.1"})
            with urlopen(req, timeout=15) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type", "")
        except Exception as exc:
            logger.warning("Failed to fetch %s: %s", url, exc)
            return -1

        text = raw.decode("utf-8", errors="replace")

        if "html" in content_type.lower() or text.strip().startswith("<!"):
            text = self._html_to_text(text)

        return self.index(label, text, source_type="url")

    def purge(self) -> None:
        """Wipe all indexed content."""
        self._conn.execute("DELETE FROM sources")
        self._conn.execute("DELETE FROM chunks")
        self._conn.execute("DELETE FROM chunks_trigram")
        self._conn.commit()
        self._vocab_cache = None

    def stats(self) -> dict[str, Any]:
        """Return source count, chunk count, total bytes."""
        source_count = self._conn.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
        chunk_count = self._conn.execute(
            "SELECT COUNT(*) FROM chunks"
        ).fetchone()[0]
        total_bytes = self._conn.execute(
            "SELECT COALESCE(SUM(total_bytes), 0) FROM sources"
        ).fetchone()[0]
        return {
            "source_count": source_count,
            "chunk_count": chunk_count,
            "total_bytes": total_bytes,
            "db_path": str(self._db_path),
        }

    # -- Private helpers --

    def _create_source(
        self, label: str, source_type: str, chunk_count: int, total_bytes: int,
    ) -> int:
        cursor = self._conn.execute(
            "INSERT INTO sources (label, source_type, chunk_count, total_bytes) "
            "VALUES (?, ?, ?, ?)",
            (label, source_type, chunk_count, total_bytes),
        )
        self._conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def _insert_chunks(self, source_id: int, chunks: list[Chunk]) -> None:
        rows = [(str(source_id), c.title, c.content) for c in chunks]
        self._conn.executemany(
            "INSERT INTO chunks (source_id, title, content) VALUES (?, ?, ?)",
            rows,
        )
        self._conn.executemany(
            "INSERT INTO chunks_trigram (source_id, title, content) VALUES (?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def _auto_chunk(self, content: str, source_type: str) -> list[Chunk]:
        """Pick chunking strategy based on source type and content heuristics."""
        if source_type == "json":
            try:
                data = json.loads(content)
                return chunk_json(data)
            except (json.JSONDecodeError, TypeError):
                pass

        # Markdown detection: presence of headers or fenced blocks
        if re.search(r"^#{1,4}\s+", content, re.MULTILINE):
            return chunk_markdown(content)

        return chunk_plaintext(content)

    def _fts5_search(
        self, table: str, query: str, limit: int,
    ) -> list[SearchResult]:
        """Run FTS5 MATCH query with BM25 ranking and snippet extraction."""
        escaped = self._escape_fts5(query)
        if not escaped:
            return []

        try:
            sql = f"""
                SELECT
                    s.label,
                    {table}.title,
                    snippet({table}, 2, '<b>', '</b>', '...', 32),
                    rank,
                    CAST({table}.source_id AS INTEGER)
                FROM {table}
                JOIN sources s ON s.id = CAST({table}.source_id AS INTEGER)
                WHERE {table} MATCH ?
                ORDER BY rank
                LIMIT ?
            """
            rows = self._conn.execute(sql, (escaped, limit)).fetchall()
        except sqlite3.OperationalError:
            # Malformed FTS query falls through to next tier
            return []

        return [
            SearchResult(
                source_label=row[0],
                title=row[1],
                snippet=row[2],
                score=abs(row[3]),  # BM25 returns negative scores
                source_id=row[4],
            )
            for row in rows
        ]

    def _fuzzy_search(self, query: str, limit: int) -> list[SearchResult]:
        """Tier 3: word-level fuzzy matching via difflib."""
        vocab = self._get_vocabulary()
        if not vocab:
            return []

        query_words = query.lower().split()
        matched_words: set[str] = set()
        for word in query_words:
            close = difflib.get_close_matches(word, vocab, n=3, cutoff=0.6)
            matched_words.update(close)

        if not matched_words:
            return []

        # Search for chunks containing any of the fuzzy-matched words
        like_clauses = " OR ".join(["content LIKE ?" for _ in matched_words])
        params = [f"%{w}%" for w in matched_words]
        params.append(str(limit))  # type: ignore[arg-type]

        sql = f"""
            SELECT s.label, c.title, substr(c.content, 1, 200), 0.5,
                   CAST(c.source_id AS INTEGER)
            FROM chunks c
            JOIN sources s ON s.id = CAST(c.source_id AS INTEGER)
            WHERE {like_clauses}
            LIMIT ?
        """
        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            return []

        return [
            SearchResult(
                source_label=row[0],
                title=row[1],
                snippet=row[2],
                score=row[3],
                source_id=row[4],
            )
            for row in rows
        ]

    def _get_vocabulary(self) -> list[str]:
        """Build vocabulary from indexed chunks for fuzzy matching."""
        if self._vocab_cache is not None:
            return self._vocab_cache

        try:
            rows = self._conn.execute(
                "SELECT content FROM chunks LIMIT 500"
            ).fetchall()
        except sqlite3.OperationalError:
            return []

        words: set[str] = set()
        for (content,) in rows:
            for word in re.findall(r"\b[a-zA-Z]{3,}\b", content):
                words.add(word.lower())

        self._vocab_cache = list(words)
        return self._vocab_cache

    @staticmethod
    def _escape_fts5(query: str) -> str:
        """Sanitize user query for FTS5 MATCH syntax."""
        # Strip special FTS5 operators, keep words
        words = re.findall(r"[\w]+", query)
        if not words:
            return ""
        # Quote each word and join with implicit AND
        return " ".join(f'"{w}"' for w in words)

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Minimal HTML to text conversion without external deps."""
        # Remove script/style blocks
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.DOTALL | re.IGNORECASE)
        # Convert common block tags to newlines
        text = re.sub(r"<(?:br|p|div|h[1-6]|li|tr)[^>]*>", "\n", text, flags=re.IGNORECASE)
        # Strip remaining tags
        text = re.sub(r"<[^>]+>", "", text)
        # Decode common entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
        # Collapse whitespace
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @staticmethod
    def _cap_results(results: list[SearchResult]) -> list[SearchResult]:
        """Enforce 40KB output cap on combined snippet size."""
        capped: list[SearchResult] = []
        total = 0
        for r in results:
            size = len(r.snippet.encode("utf-8"))
            if total + size > _SEARCH_OUTPUT_CAP:
                remaining = _SEARCH_OUTPUT_CAP - total
                if remaining > 100:
                    r = SearchResult(
                        source_label=r.source_label,
                        title=r.title,
                        snippet=r.snippet[:remaining],
                        score=r.score,
                        source_id=r.source_id,
                    )
                    capped.append(r)
                break
            capped.append(r)
            total += size
        return capped
