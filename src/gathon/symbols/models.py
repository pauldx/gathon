"""Data models for the symbol indexing engine."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field


@dataclass
class SymbolInfo:
    name: str
    qualified_name: str
    kind: str  # function, class, method, variable
    file_path: str
    line_start: int
    line_end: int
    language: str
    signature: str = ""
    params: list[str] = field(default_factory=list)
    return_type: str = ""
    decorators: list[str] = field(default_factory=list)
    docstring: str = ""
    parent_name: str = ""
    body_hash: str = ""
    is_test: bool = False


@dataclass
class SymbolDependency:
    source_symbol: str
    target_symbol: str
    kind: str  # calls, imports, inherits, references


@dataclass
class ImportInfo:
    module: str
    names: list[str] = field(default_factory=list)
    line: int = 0
    is_from: bool = False


@dataclass
class FileSymbols:
    file_path: str
    language: str
    symbols: list[SymbolInfo] = field(default_factory=list)
    imports: list[ImportInfo] = field(default_factory=list)
    mtime: float = 0.0


def compute_body_hash(body: str) -> str:
    """Normalize body text and return SHA256[:16]."""
    lines = body.splitlines()
    if not lines:
        return hashlib.sha256(b"").hexdigest()[:16]
    # strip common leading whitespace
    min_indent = float("inf")
    for line in lines:
        stripped = line.lstrip()
        if stripped:
            min_indent = min(min_indent, len(line) - len(stripped))
    if min_indent == float("inf"):
        min_indent = 0
    normalized = "\n".join(line[min_indent:] for line in lines)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
