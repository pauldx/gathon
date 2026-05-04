"""UnifiedStore — extends GraphStore with gathon columns and new tables."""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import networkx as nx
from gathon.code_graph.graph import GraphStore
from gathon.code_graph.migrations import get_schema_version

from gathon.schema import UnifiedEdge, UnifiedNode

logger = logging.getLogger(__name__)

GATHON_MIGRATIONS: dict[int, str] = {
    10: """
        ALTER TABLE nodes ADD COLUMN label TEXT DEFAULT '';
        ALTER TABLE nodes ADD COLUMN file_type TEXT DEFAULT 'code';
        ALTER TABLE nodes ADD COLUMN source_url TEXT DEFAULT '';
        ALTER TABLE nodes ADD COLUMN source_location TEXT DEFAULT '';
        ALTER TABLE nodes ADD COLUMN confidence TEXT DEFAULT 'EXTRACTED';
        ALTER TABLE nodes ADD COLUMN confidence_score REAL DEFAULT 1.0;
        ALTER TABLE nodes ADD COLUMN pipeline TEXT DEFAULT '';
        ALTER TABLE nodes ADD COLUMN captured_at TEXT DEFAULT '';
        ALTER TABLE nodes ADD COLUMN author TEXT DEFAULT '';

        ALTER TABLE edges ADD COLUMN relation TEXT DEFAULT '';
        ALTER TABLE edges ADD COLUMN weight REAL DEFAULT 1.0;

        CREATE TABLE IF NOT EXISTS hyperedges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            label TEXT NOT NULL,
            node_ids TEXT NOT NULL,
            source_file TEXT,
            created_at TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT NOT NULL,
            pipeline TEXT NOT NULL,
            file_hash TEXT NOT NULL,
            node_count INTEGER DEFAULT 0,
            edge_count INTEGER DEFAULT 0,
            duration_ms INTEGER DEFAULT 0,
            ran_at TEXT DEFAULT (datetime('now'))
        );
    """,
    11: """
        CREATE INDEX IF NOT EXISTS idx_nodes_file_type ON nodes(file_type);
        CREATE INDEX IF NOT EXISTS idx_nodes_pipeline ON nodes(pipeline);
        CREATE INDEX IF NOT EXISTS idx_nodes_confidence ON nodes(confidence);
        CREATE INDEX IF NOT EXISTS idx_edges_relation ON edges(relation);
        CREATE INDEX IF NOT EXISTS idx_pipeline_runs_file ON pipeline_runs(file_path);
        CREATE INDEX IF NOT EXISTS idx_pipeline_runs_hash ON pipeline_runs(file_hash);
        CREATE INDEX IF NOT EXISTS idx_hyperedges_label ON hyperedges(label);
    """,
    12: """
        ALTER TABLE nodes ADD COLUMN compressed_label TEXT DEFAULT '';
    """,
    13: """
        ALTER TABLE nodes ADD COLUMN content_hash TEXT DEFAULT '';
        CREATE INDEX IF NOT EXISTS idx_nodes_content_hash
            ON nodes(content_hash);
    """,
    14: """
        CREATE TABLE IF NOT EXISTS compression_telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tool_name TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'compress',
            before_tokens INTEGER NOT NULL DEFAULT 0,
            after_tokens INTEGER NOT NULL DEFAULT 0,
            savings_tokens INTEGER NOT NULL DEFAULT 0,
            savings_pct REAL NOT NULL DEFAULT 0.0,
            intensity TEXT NOT NULL DEFAULT 'off',
            detail_level TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS idx_telemetry_tool
            ON compression_telemetry(tool_name);
        CREATE INDEX IF NOT EXISTS idx_telemetry_created
            ON compression_telemetry(created_at);
        CREATE INDEX IF NOT EXISTS idx_telemetry_event
            ON compression_telemetry(event_type);
    """,
}

GATHON_LATEST = max(GATHON_MIGRATIONS.keys())


def _run_gathon_migrations(conn: sqlite3.Connection) -> None:
    current = get_schema_version(conn)
    if current >= GATHON_LATEST:
        return

    for version in sorted(GATHON_MIGRATIONS.keys()):
        if version <= current:
            continue
        logger.info("Running gathon migration v%d", version)
        try:
            for stmt in GATHON_MIGRATIONS[version].strip().split(";"):
                stmt = stmt.strip()
                if stmt:
                    conn.execute(stmt)
            conn.execute(
                "INSERT OR REPLACE INTO metadata (key, value) VALUES ('schema_version', ?)",
                (str(version),),
            )
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            logger.error("Gathon migration v%d failed", version, exc_info=True)
            raise

    logger.info("Gathon migrations complete, now at v%d", GATHON_LATEST)


_COMPRESSIBLE_FILE_TYPES = frozenset({
    "document", "paper", "image", "video", "api_spec",
})


def _compute_content_hash(node: UnifiedNode) -> str:
    """SHA256 of content-significant fields for dedup detection."""
    parts = f"{node.kind}|{node.name}|{node.label}|{node.file_type}"
    return hashlib.sha256(parts.encode()).hexdigest()[:16]


class UnifiedStore(GraphStore):
    """SQLite store combining graph schema with gathon extensions."""

    def __init__(
        self,
        db_path: str | Path,
        compress_intensity: str = "off",
    ) -> None:
        super().__init__(db_path)
        _run_gathon_migrations(self._conn)
        self._migrate_pipeline_names()
        self._nx_graph: nx.DiGraph | None = None
        self._nx_dirty = True
        self._compress_intensity = compress_intensity

    def _migrate_pipeline_names(self) -> None:
        updates = self._conn.execute(
            "UPDATE nodes SET pipeline = REPLACE(pipeline, 'graphify_', 'gathon_')"
        ).rowcount
        if updates > 0:
            logger.info("Migrated %d node pipeline names from graphify_* to gathon_*", updates)
        updates = self._conn.execute(
            "UPDATE pipeline_runs SET pipeline = REPLACE(pipeline, 'graphify_', 'gathon_')"
        ).rowcount
        if updates > 0:
            logger.info("Migrated %d pipeline_runs names from graphify_* to gathon_*", updates)
        # Migrate crg_code → code_graph
        updates = self._conn.execute(
            "UPDATE nodes SET pipeline = 'code_graph' WHERE pipeline = 'crg_code'"
        ).rowcount
        if updates > 0:
            logger.info("Migrated %d node pipeline names from crg_code to code_graph", updates)
        updates = self._conn.execute(
            "UPDATE pipeline_runs SET pipeline = 'code_graph' WHERE pipeline = 'crg_code'"
        ).rowcount
        if updates > 0:
            logger.info("Migrated %d pipeline_runs from crg_code to code_graph", updates)
        self._conn.commit()

    def upsert_unified_node(self, node: UnifiedNode, file_hash: str = "") -> int:
        now = datetime.now(UTC).timestamp()
        chash = _compute_content_hash(node)

        # Dedup: skip write if content unchanged for same qualified_name
        existing = self._conn.execute(
            "SELECT id, content_hash FROM nodes WHERE qualified_name = ?",
            (node.qualified_name,),
        ).fetchone()
        if existing and existing[1] == chash:
            return existing[0]

        compressed_label = ""
        if (
            self._compress_intensity != "off"
            and node.file_type in _COMPRESSIBLE_FILE_TYPES
            and node.label
        ):
            from gathon.compress import compress_text
            compressed_label = compress_text(
                node.label, self._compress_intensity,
            )

        self._conn.execute(
            """INSERT INTO nodes (
                kind, name, qualified_name, file_path, line_start, line_end,
                language, parent_name, params, return_type, modifiers, is_test,
                file_hash, extra, updated_at, label, file_type, source_url,
                source_location, confidence, confidence_score, pipeline,
                captured_at, author, compressed_label, content_hash
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            ON CONFLICT(qualified_name) DO UPDATE SET
                kind=excluded.kind, name=excluded.name, file_path=excluded.file_path,
                line_start=excluded.line_start, line_end=excluded.line_end,
                language=excluded.language, parent_name=excluded.parent_name,
                params=excluded.params, return_type=excluded.return_type,
                modifiers=excluded.modifiers, is_test=excluded.is_test,
                file_hash=excluded.file_hash, extra=excluded.extra,
                updated_at=excluded.updated_at, label=excluded.label,
                file_type=excluded.file_type, source_url=excluded.source_url,
                source_location=excluded.source_location,
                confidence=excluded.confidence,
                confidence_score=excluded.confidence_score,
                pipeline=excluded.pipeline, captured_at=excluded.captured_at,
                author=excluded.author,
                compressed_label=excluded.compressed_label,
                content_hash=excluded.content_hash
            """,
            (
                node.kind, node.name, node.qualified_name, node.file_path,
                node.line_start, node.line_end, node.language, node.parent_name,
                node.params, node.return_type, node.modifiers, int(node.is_test),
                file_hash, str(node.extra) if node.extra else "{}",
                now, node.label, node.file_type, node.source_url,
                node.source_location, node.confidence, node.confidence_score,
                node.pipeline, node.captured_at, node.author,
                compressed_label, chash,
            ),
        )
        self._nx_dirty = True
        row = self._conn.execute(
            "SELECT id FROM nodes WHERE qualified_name = ?", (node.qualified_name,)
        ).fetchone()
        return row[0] if row else -1

    def upsert_unified_edge(self, edge: UnifiedEdge) -> int:
        now = datetime.now(UTC).timestamp()
        extra = str(edge.extra) if edge.extra else "{}"
        edge_where = (
            "SELECT id FROM edges WHERE kind=? AND source_qualified=?"
            " AND target_qualified=? AND file_path=? AND line=?"
        )
        edge_params = (
            edge.kind, edge.source_qualified, edge.target_qualified,
            edge.file_path, edge.line,
        )
        row = self._conn.execute(edge_where, edge_params).fetchone()

        if row:
            self._conn.execute(
                """UPDATE edges SET extra=?, confidence=?,
                   confidence_tier=?, updated_at=?, relation=?,
                   weight=? WHERE id=?""",
                (
                    extra, edge.confidence, edge.confidence_tier,
                    now, edge.relation, edge.weight, row[0],
                ),
            )
            self._nx_dirty = True
            return row[0]

        self._conn.execute(
            """INSERT INTO edges (
                kind, source_qualified, target_qualified, file_path, line,
                extra, confidence, confidence_tier, updated_at, relation, weight
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge.kind, edge.source_qualified, edge.target_qualified,
                edge.file_path, edge.line, extra,
                edge.confidence, edge.confidence_tier, now, edge.relation, edge.weight,
            ),
        )
        self._nx_dirty = True
        new_row = self._conn.execute(
            edge_where, edge_params,
        ).fetchone()
        return new_row[0] if new_row else -1

    def store_unified_file(
        self,
        file_path: str,
        nodes: list[UnifiedNode],
        edges: list[UnifiedEdge],
        file_hash: str = "",
        pipeline: str = "",
        duration_ms: int = 0,
    ) -> None:
        """Atomically replace all unified data for a file."""
        self._conn.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))
        self._conn.execute("DELETE FROM edges WHERE file_path = ?", (file_path,))

        for node in nodes:
            self.upsert_unified_node(node, file_hash)
        for edge in edges:
            self.upsert_unified_edge(edge)

        if pipeline:
            self._conn.execute(
                """INSERT INTO pipeline_runs
                (file_path, pipeline, file_hash,
                 node_count, edge_count, duration_ms)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (file_path, pipeline, file_hash, len(nodes), len(edges), duration_ms),
            )

        self._nx_dirty = True

    def store_extraction_dict(self, data: dict[str, Any], pipeline: str = "") -> None:
        """Accept gathon extraction dict, adapt, and store."""
        from gathon.adapters.extraction import adapt_extraction

        nodes, edges = adapt_extraction(data)
        for node in nodes:
            self.upsert_unified_node(node)
        for edge in edges:
            self.upsert_unified_edge(edge)
        self._nx_dirty = True

    def get_pipeline_run(self, file_path: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE file_path = ? ORDER BY ran_at DESC LIMIT 1",
            (file_path,),
        ).fetchone()
        if not row:
            return None
        cols = [d[0] for d in self._conn.execute("SELECT * FROM pipeline_runs LIMIT 0").description]
        return dict(zip(cols, row))

    def build_networkx_graph(self) -> nx.DiGraph:
        """Materialize full graph as NetworkX DiGraph. Cached until writes invalidate."""
        if self._nx_graph is not None and not self._nx_dirty:
            return self._nx_graph

        g = nx.DiGraph()
        node_sql = (
            "SELECT qualified_name, kind, name, file_path,"
            " file_type, pipeline FROM nodes"
        )
        for row in self._conn.execute(node_sql):
            qn, kind, name, fp, ft, pipe = row
            g.add_node(
                qn, kind=kind, name=name, file_path=fp,
                file_type=ft, pipeline=pipe,
            )

        edge_sql = (
            "SELECT source_qualified, target_qualified, kind,"
            " relation, weight, confidence FROM edges"
        )
        for row in self._conn.execute(edge_sql):
            src, tgt, kind, rel, w, conf = row
            if g.has_node(src) and g.has_node(tgt):
                g.add_edge(src, tgt, kind=kind, relation=rel, weight=w, confidence=conf)

        self._nx_graph = g
        self._nx_dirty = False
        return g

    def get_unified_stats(self) -> dict[str, Any]:
        base = self.get_stats()
        pipeline_counts = {}
        for row in self._conn.execute("SELECT pipeline, COUNT(*) FROM nodes GROUP BY pipeline"):
            pipeline_counts[row[0] or "unknown"] = row[1]

        file_type_counts = {}
        for row in self._conn.execute("SELECT file_type, COUNT(*) FROM nodes GROUP BY file_type"):
            file_type_counts[row[0] or "unknown"] = row[1]

        confidence_counts = {}
        for row in self._conn.execute("SELECT confidence, COUNT(*) FROM nodes GROUP BY confidence"):
            confidence_counts[row[0] or "unknown"] = row[1]

        return {
            "total_nodes": base.total_nodes,
            "total_edges": base.total_edges,
            "nodes_by_kind": base.nodes_by_kind,
            "edges_by_kind": base.edges_by_kind,
            "languages": base.languages,
            "files_count": base.files_count,
            "nodes_by_pipeline": pipeline_counts,
            "nodes_by_file_type": file_type_counts,
            "nodes_by_confidence": confidence_counts,
        }
