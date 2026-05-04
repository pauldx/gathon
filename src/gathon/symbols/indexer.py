"""SymbolIndex: SQLite-backed symbol indexing engine."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from pathlib import Path

from .models import FileSymbols, ImportInfo, SymbolDependency, SymbolInfo
from .parsers import EXTENSION_MAP, detect_language, parse_file

SKIP_DIRS = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", "*.egg-info",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    qualified_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    file_path TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    language TEXT NOT NULL,
    signature TEXT DEFAULT '',
    params TEXT DEFAULT '[]',
    return_type TEXT DEFAULT '',
    decorators TEXT DEFAULT '[]',
    docstring TEXT DEFAULT '',
    parent_name TEXT DEFAULT '',
    body_hash TEXT DEFAULT '',
    is_test INTEGER DEFAULT 0,
    indexed_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS dependencies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_symbol TEXT NOT NULL,
    target_symbol TEXT NOT NULL,
    kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT NOT NULL,
    module TEXT NOT NULL,
    names TEXT DEFAULT '[]',
    line INTEGER NOT NULL,
    is_from INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS file_index (
    file_path TEXT PRIMARY KEY,
    mtime REAL NOT NULL,
    language TEXT NOT NULL,
    symbol_count INTEGER DEFAULT 0,
    indexed_at REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS idx_symbols_qualified ON symbols(qualified_name);
CREATE INDEX IF NOT EXISTS idx_symbols_file ON symbols(file_path);
CREATE INDEX IF NOT EXISTS idx_symbols_kind ON symbols(kind);
CREATE INDEX IF NOT EXISTS idx_deps_source ON dependencies(source_symbol);
CREATE INDEX IF NOT EXISTS idx_deps_target ON dependencies(target_symbol);
CREATE INDEX IF NOT EXISTS idx_imports_file ON imports(file_path);
CREATE INDEX IF NOT EXISTS idx_file_index_path ON file_index(file_path);
"""


def _project_hash(project_root: str) -> str:
    return hashlib.sha256(os.path.abspath(project_root).encode("utf-8")).hexdigest()[:12]


def _db_path(project_root: str) -> Path:
    base = Path.home() / ".gathon" / "symbols"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{_project_hash(project_root)}.db"


class SymbolIndex:
    """SQLite-backed symbol index with tree-sitter parsing."""

    def __init__(self, project_root: str | None = None, db_path: str | None = None):
        if db_path:
            self._db_path = Path(db_path)
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        elif project_root:
            self._db_path = _db_path(project_root)
        else:
            raise ValueError("Either project_root or db_path must be provided")

        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def index_file(self, file_path: str, project_root: str | None = None) -> FileSymbols | None:
        """Parse and index a single file. Returns None if skipped (unchanged)."""
        abs_path = os.path.abspath(file_path)
        language = detect_language(abs_path)
        if language is None:
            return None

        mtime = os.path.getmtime(abs_path)

        # Check if file is already indexed and unchanged
        row = self._conn.execute(
            "SELECT mtime FROM file_index WHERE file_path = ?", (abs_path,)
        ).fetchone()
        if row and row[0] >= mtime:
            return None

        fs = parse_file(abs_path, language)
        now = time.time()

        # Clear old data for this file
        self._conn.execute("DELETE FROM symbols WHERE file_path = ?", (abs_path,))
        self._conn.execute("DELETE FROM imports WHERE file_path = ?", (abs_path,))
        # Clear dependencies sourced from symbols in this file
        self._conn.execute(
            "DELETE FROM dependencies WHERE source_symbol IN "
            "(SELECT qualified_name FROM symbols WHERE file_path = ?)",
            (abs_path,),
        )

        # Insert symbols
        for sym in fs.symbols:
            self._conn.execute(
                """INSERT INTO symbols
                (name, qualified_name, kind, file_path, line_start, line_end,
                 language, signature, params, return_type, decorators, docstring,
                 parent_name, body_hash, is_test, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sym.name, sym.qualified_name, sym.kind, abs_path,
                    sym.line_start, sym.line_end, sym.language, sym.signature,
                    json.dumps(sym.params), sym.return_type,
                    json.dumps(sym.decorators), sym.docstring,
                    sym.parent_name, sym.body_hash, int(sym.is_test), now,
                ),
            )

        # Insert imports
        for imp in fs.imports:
            self._conn.execute(
                "INSERT INTO imports "
                "(file_path, module, names, line, is_from) "
                "VALUES (?, ?, ?, ?, ?)",
                (abs_path, imp.module, json.dumps(imp.names), imp.line, int(imp.is_from)),
            )

        # Update file_index
        self._conn.execute(
            "INSERT OR REPLACE INTO file_index "
            "(file_path, mtime, language, symbol_count, indexed_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (abs_path, mtime, language, len(fs.symbols), now),
        )

        # Extract dependencies between symbols
        self._extract_dependencies(abs_path, fs)

        self._conn.commit()
        return fs

    def index_project(
        self, project_root: str, file_patterns: list[str] | None = None,
    ) -> dict:
        """Walk project and index all supported files."""
        root = os.path.abspath(project_root)
        indexed = 0
        skipped = 0
        errors = 0
        extensions = set(EXTENSION_MAP.keys())

        if file_patterns:
            import fnmatch

            def _pattern_check(f: str) -> bool:
                return any(fnmatch.fnmatch(f, p) for p in file_patterns)
        else:
            def _pattern_check(f: str) -> bool:
                return True

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories
            dirnames[:] = [
                d for d in dirnames
                if d not in SKIP_DIRS and not d.endswith(".egg-info")
            ]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in extensions:
                    continue

                full_path = os.path.join(dirpath, fname)
                if not _pattern_check(full_path):
                    continue

                try:
                    result = self.index_file(full_path, root)
                    if result is not None:
                        indexed += 1
                    else:
                        skipped += 1
                except Exception:
                    errors += 1

        return {"indexed": indexed, "skipped": skipped, "errors": errors}

    def _extract_dependencies(self, file_path: str, fs: FileSymbols):
        """Extract call/import/inherit dependencies from parsed symbols."""
        # Build a set of known symbol names for cross-referencing
        known_names: set[str] = set()
        cursor = self._conn.execute("SELECT name, qualified_name FROM symbols")
        for row in cursor:
            known_names.add(row[0])
            known_names.add(row[1])

        # Add current file's symbols
        for sym in fs.symbols:
            known_names.add(sym.name)
            known_names.add(sym.qualified_name)

        # Import-based dependencies
        for imp in fs.imports:
            for name in imp.names:
                if name in known_names:
                    # Find symbols in this file that might use this import
                    for sym in fs.symbols:
                        if sym.kind in ("function", "method"):
                            self._conn.execute(
                                "INSERT INTO dependencies (source_symbol, target_symbol, kind) "
                                "VALUES (?, ?, ?)",
                                (sym.qualified_name, name, "imports"),
                            )
                            break

        # Inheritance dependencies (classes with bases)
        for sym in fs.symbols:
            if sym.kind == "class" and sym.params:
                for base in sym.params:
                    base_name = base.strip().split("(")[0].split("[")[0]
                    if base_name and base_name in known_names:
                        self._conn.execute(
                            "INSERT INTO dependencies (source_symbol, target_symbol, kind) "
                            "VALUES (?, ?, ?)",
                            (sym.qualified_name, base_name, "inherits"),
                        )

        # Call-based dependencies (simple heuristic: scan source lines within function bodies)
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                source_lines = f.readlines()
        except OSError:
            return

        func_symbols = [s for s in fs.symbols if s.kind in ("function", "method")]
        for sym in func_symbols:
            body_lines = source_lines[sym.line_start - 1:sym.line_end]
            body_text = "".join(body_lines)
            # Find function-call-like patterns: word followed by (
            call_pattern = r"\b(\w+)\s*\("
            import re
            for match in re.finditer(call_pattern, body_text):
                callee = match.group(1)
                # Skip keywords and the function's own name
                if callee in ("if", "for", "while", "return", "print", "range",
                              "len", "str", "int", "float", "list", "dict",
                              "set", "tuple", "type", "isinstance", "hasattr",
                              "getattr", "setattr", "super", "property",
                              sym.name):
                    continue
                if callee in known_names:
                    self._conn.execute(
                        "INSERT INTO dependencies (source_symbol, target_symbol, kind) "
                        "VALUES (?, ?, ?)",
                        (sym.qualified_name, callee, "calls"),
                    )

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def find_symbol(self, name: str, exact: bool = False) -> list[SymbolInfo]:
        """Search symbols by name or qualified_name."""
        if exact:
            cursor = self._conn.execute(
                "SELECT * FROM symbols WHERE name = ? OR qualified_name = ?",
                (name, name),
            )
        else:
            pattern = f"%{name}%"
            cursor = self._conn.execute(
                "SELECT * FROM symbols WHERE name LIKE ? OR qualified_name LIKE ?",
                (pattern, pattern),
            )
        return [self._row_to_symbol(row) for row in cursor.fetchall()]

    def get_function_source(self, name: str, level: int = 0) -> str:
        """Get function source. level: 0=full body, 1=signature+docstring, 2=signature only."""
        symbols = self.find_symbol(name, exact=True)
        funcs = [s for s in symbols if s.kind in ("function", "method")]
        if not funcs:
            return ""
        sym = funcs[0]
        return self._get_source(sym, level)

    def get_class_source(self, name: str, level: int = 0) -> str:
        """Get class source. level: 0=full, 1=signature+methods, 2=signature only."""
        symbols = self.find_symbol(name, exact=True)
        classes = [s for s in symbols if s.kind == "class"]
        if not classes:
            return ""
        sym = classes[0]

        if level == 2:
            return sym.signature

        try:
            with open(sym.file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return sym.signature

        body_lines = lines[sym.line_start - 1:sym.line_end]

        if level == 0:
            return "".join(body_lines)

        # level 1: signature + method signatures
        result = [sym.signature + "\n"]
        if sym.docstring:
            result.append(f'    """{sym.docstring}"""\n')

        methods = self.find_symbol(name, exact=False)
        for m in methods:
            if m.kind == "method" and m.parent_name == sym.name:
                result.append(f"    {m.signature}\n")
                if m.docstring:
                    result.append(f'        """{m.docstring}"""\n')
                result.append("        ...\n")

        return "".join(result)

    def get_symbols_in_file(self, file_path: str) -> list[SymbolInfo]:
        abs_path = os.path.abspath(file_path)
        cursor = self._conn.execute(
            "SELECT * FROM symbols WHERE file_path = ? ORDER BY line_start",
            (abs_path,),
        )
        return [self._row_to_symbol(row) for row in cursor.fetchall()]

    def get_dependencies(self, symbol_name: str) -> list[SymbolDependency]:
        """What this symbol calls/imports/inherits."""
        cursor = self._conn.execute(
            "SELECT source_symbol, target_symbol, kind FROM dependencies "
            "WHERE source_symbol = ? OR source_symbol LIKE ?",
            (symbol_name, f"%.{symbol_name}"),
        )
        return [
            SymbolDependency(source_symbol=r[0], target_symbol=r[1], kind=r[2])
            for r in cursor.fetchall()
        ]

    def get_dependents(self, symbol_name: str) -> list[SymbolDependency]:
        """Who calls/references this symbol."""
        cursor = self._conn.execute(
            "SELECT source_symbol, target_symbol, kind FROM dependencies "
            "WHERE target_symbol = ? OR target_symbol LIKE ?",
            (symbol_name, f"%.{symbol_name}"),
        )
        return [
            SymbolDependency(source_symbol=r[0], target_symbol=r[1], kind=r[2])
            for r in cursor.fetchall()
        ]

    def get_imports(self, file_path: str) -> list[ImportInfo]:
        abs_path = os.path.abspath(file_path)
        cursor = self._conn.execute(
            "SELECT module, names, line, is_from FROM imports WHERE file_path = ? ORDER BY line",
            (abs_path,),
        )
        return [
            ImportInfo(
                module=r[0],
                names=json.loads(r[1]),
                line=r[2],
                is_from=bool(r[3]),
            )
            for r in cursor.fetchall()
        ]

    def get_stale_files(self, project_root: str) -> list[str]:
        """Files where current mtime > indexed mtime."""
        root = os.path.abspath(project_root)
        stale = []
        cursor = self._conn.execute("SELECT file_path, mtime FROM file_index")
        for file_path, indexed_mtime in cursor.fetchall():
            if not file_path.startswith(root):
                continue
            try:
                current_mtime = os.path.getmtime(file_path)
                if current_mtime > indexed_mtime:
                    stale.append(file_path)
            except OSError:
                stale.append(file_path)
        return stale

    def stats(self) -> dict:
        sym_count = self._conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
        file_count = self._conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0]
        dep_count = self._conn.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0]
        lang_rows = self._conn.execute(
            "SELECT language, COUNT(*) FROM file_index GROUP BY language"
        ).fetchall()
        languages = {r[0]: r[1] for r in lang_rows}
        return {
            "symbol_count": sym_count,
            "file_count": file_count,
            "dependency_count": dep_count,
            "languages": languages,
        }

    def close(self):
        self._conn.close()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_source(self, sym: SymbolInfo, level: int) -> str:
        if level == 2:
            return sym.signature

        try:
            with open(sym.file_path, encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return sym.signature

        body_lines = lines[sym.line_start - 1:sym.line_end]

        if level == 0:
            return "".join(body_lines)

        # level 1: signature + docstring
        result = sym.signature + "\n"
        if sym.docstring:
            result += f'    """{sym.docstring}"""\n'
        return result

    def _row_to_symbol(self, row: tuple) -> SymbolInfo:
        return SymbolInfo(
            name=row[1],
            qualified_name=row[2],
            kind=row[3],
            file_path=row[4],
            line_start=row[5],
            line_end=row[6],
            language=row[7],
            signature=row[8],
            params=json.loads(row[9]) if row[9] else [],
            return_type=row[10] or "",
            decorators=json.loads(row[11]) if row[11] else [],
            docstring=row[12] or "",
            parent_name=row[13] or "",
            body_hash=row[14] or "",
            is_test=bool(row[15]),
        )
