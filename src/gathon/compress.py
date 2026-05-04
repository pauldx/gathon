"""Token compression for tool responses and stored text.

Two entry points:
- compress_tool_response(data, intensity) — post-process MCP tool output dicts
- compress_text(text, intensity) — compress a single text string

Intensity levels: lite, full (default), ultra.
Preserves: code blocks, inline code, URLs, file paths, qualified names, numbers.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

# === Intensity Levels ===


class Intensity(StrEnum):
    LITE = "lite"
    FULL = "full"
    ULTRA = "ultra"
    OFF = "off"


# === Preservation Patterns ===

# Fenced code blocks (``` or ~~~)
_CODE_BLOCK_RE = re.compile(
    r"(`{3,}|~{3,})[^\n]*\n.*?\n\1", re.DOTALL,
)

# Inline code `...`
_INLINE_CODE_RE = re.compile(r"`[^`]+`")

# URLs
_URL_RE = re.compile(r"https?://[^\s)>\]]+")

# File paths: /foo/bar, ./foo, ../foo, foo/bar.py, C:\foo
_PATH_RE = re.compile(
    r"(?:\./|\.\./|/|[A-Za-z]:\\)[\w\-/\\.]+"
    r"|[\w\-.]+[/\\][\w\-/\\.]+"
)

# Qualified names: module::Class.method, file.py::func
_QUALIFIED_NAME_RE = re.compile(r"[\w./]+::[\w.]+")

# Numbers with optional units: 42, 3.14, 100ms, 2KB
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?(?:\s*(?:ms|s|KB|MB|GB|TB|%))?(?=\s|$|[,;.])")

# === Word Lists ===

_ARTICLES = {"a", "an", "the"}

_FILLERS = {
    "just", "really", "basically", "actually", "simply",
    "essentially", "generally", "literally", "certainly",
    "obviously", "probably", "typically", "usually",
    "definitely", "particularly", "specifically",
}

_PLEASANTRIES_RE = re.compile(
    r"\b(?:"
    r"sure[,!.]?\s*"
    r"|of course[,!.]?\s*"
    r"|happy to\s+"
    r"|glad to\s+"
    r"|i'd be happy to[^.]*\.\s*"
    r"|i'd recommend\s+"
    r"|please note that\s+"
    r"|it's worth noting that\s+"
    r"|it should be noted that\s+"
    r"|as you (?:can see|know|may know)[,]?\s*"
    r")",
    re.IGNORECASE,
)

_HEDGING_RE = re.compile(
    r"\b(?:"
    r"it might be worth\s+"
    r"|you could consider\s+"
    r"|you may want to\s+"
    r"|it would be possible to\s+"
    r"|it seems like\s+"
    r"|it appears that\s+"
    r"|in my opinion[,]?\s*"
    r"|i think that?\s+"
    r"|i believe that?\s+"
    r"|(?:this|that|it) (?:is|was) (?:likely|probably)\s+"
    r")",
    re.IGNORECASE,
)

_PHRASE_REPLACEMENTS = {
    "in order to": "to",
    "make sure to": "ensure",
    "make sure that": "ensure",
    "due to the fact that": "because",
    "at this point in time": "now",
    "in the event that": "if",
    "for the purpose of": "for",
    "with respect to": "re",
    "as a result of": "from",
    "on the other hand": "alternatively",
    "in addition to": "plus",
    "a large number of": "many",
    "a small number of": "few",
    "is able to": "can",
    "is not able to": "can't",
    "has the ability to": "can",
    "in spite of": "despite",
    "with regard to": "re",
    "for example": "e.g.",
    "such as": "e.g.",
    "that is to say": "i.e.",
    "as well as": "and",
}

# Ultra abbreviations
_ULTRA_ABBREVIATIONS = {
    "database": "DB",
    "authentication": "auth",
    "authorization": "authz",
    "configuration": "config",
    "request": "req",
    "response": "res",
    "function": "fn",
    "implementation": "impl",
    "application": "app",
    "repository": "repo",
    "directory": "dir",
    "environment": "env",
    "dependency": "dep",
    "dependencies": "deps",
    "parameter": "param",
    "parameters": "params",
    "argument": "arg",
    "arguments": "args",
    "document": "doc",
    "documents": "docs",
    "information": "info",
    "specification": "spec",
    "specifications": "specs",
    "development": "dev",
    "production": "prod",
    "connection": "conn",
    "connections": "conns",
    "component": "comp",
    "components": "comps",
    "middleware": "mw",
    "approximately": "~",
    "administrator": "admin",
    "management": "mgmt",
}

_CONNECTIVE_FLUFF = {
    "however", "furthermore", "additionally", "moreover",
    "consequently", "nevertheless", "nonetheless",
    "accordingly",
}


# === Core Compression Engine ===


def _extract_preservables(text: str) -> tuple[str, dict[str, str]]:
    """Replace preservable spans with placeholders, return map to restore."""
    placeholders: dict[str, str] = {}
    counter = 0

    def _replace(match: re.Match) -> str:
        nonlocal counter
        key = f"\x00PRESERVE_{counter}\x00"
        counter += 1
        placeholders[key] = match.group(0)
        return key

    text = _CODE_BLOCK_RE.sub(_replace, text)
    text = _INLINE_CODE_RE.sub(_replace, text)
    text = _URL_RE.sub(_replace, text)
    text = _QUALIFIED_NAME_RE.sub(_replace, text)
    text = _PATH_RE.sub(_replace, text)
    text = _NUMBER_RE.sub(_replace, text)

    return text, placeholders


def _restore_preservables(text: str, placeholders: dict[str, str]) -> str:
    """Restore preserved spans from placeholders."""
    for key, original in placeholders.items():
        text = text.replace(key, original)
    return text


def _compress_lite(text: str) -> str:
    """Lite: drop filler/hedging, keep articles + full sentences."""
    text = _PLEASANTRIES_RE.sub("", text)
    text = _HEDGING_RE.sub("", text)

    for old, new in _PHRASE_REPLACEMENTS.items():
        text = re.sub(re.escape(old), new, text, flags=re.IGNORECASE)

    words = text.split()
    words = [w for w in words if w.lower().rstrip(".,;:!?") not in _FILLERS]
    text = " ".join(words)

    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _compress_full(text: str) -> str:
    """Full: drop articles, fragments OK, short synonyms."""
    text = _compress_lite(text)

    words = text.split()
    words = [w for w in words if w.lower().rstrip(".,;:!?") not in _ARTICLES]
    text = " ".join(words)

    # Drop sentence-starting connective fluff
    for word in _CONNECTIVE_FLUFF:
        text = re.sub(
            rf"\b{word}[,]?\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )

    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _compress_ultra(text: str) -> str:
    """Ultra: abbreviate, strip conjunctions, arrows for causality."""
    text = _compress_full(text)

    for full_word, abbrev in _ULTRA_ABBREVIATIONS.items():
        text = re.sub(
            rf"\b{full_word}\b",
            abbrev,
            text,
            flags=re.IGNORECASE,
        )

    # "X because Y" → "X → Y"
    text = re.sub(r"\s+because\s+", " → ", text)
    text = re.sub(r"\s+therefore\s+", " → ", text)
    text = re.sub(r"\s+so that\s+", " → ", text)
    text = re.sub(r"\s+which leads to\s+", " → ", text)
    text = re.sub(r"\s+which causes\s+", " → ", text)
    text = re.sub(r"\s+resulting in\s+", " → ", text)

    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def compress_text(text: str, intensity: str = "full") -> str:
    """Compress a text string.

    Preserves code blocks, inline code, URLs, file paths,
    qualified names, and numbers.
    """
    if not text or intensity == Intensity.OFF:
        return text

    text, placeholders = _extract_preservables(text)

    if intensity == Intensity.LITE:
        text = _compress_lite(text)
    elif intensity == Intensity.ULTRA:
        text = _compress_ultra(text)
    else:
        text = _compress_full(text)

    return _restore_preservables(text, placeholders)


# === Dict/Tool Response Compression ===

# Keys that should never be compressed (structural, numeric, IDs)
_SKIP_KEYS = frozenset({
    "kind", "type", "pipeline", "language", "format",
    "qualified_name", "file_path", "file_type", "source",
    "target", "id", "flow_id", "community_id", "node_id",
    "color", "status", "version", "schema_version",
    "line_start", "line_end", "line", "count", "total",
    "total_nodes", "total_edges", "files_count", "length",
    "weight", "score", "confidence", "confidence_score",
    "connected", "is_valid", "notes_written",
    "node_count", "edge_count", "nodes", "edges",
})

# Keys whose string values should be compressed
_TEXT_KEYS = frozenset({
    "name", "label", "description", "summary", "content",
    "text", "message", "detail", "reason", "explanation",
    "title", "body", "relation", "question",
})


def _compress_value(value: Any, intensity: str) -> Any:
    """Recursively compress string values in dicts/lists."""
    if isinstance(value, str) and len(value) > 20:
        return compress_text(value, intensity)
    if isinstance(value, dict):
        return _compress_dict(value, intensity)
    if isinstance(value, list):
        return [_compress_value(v, intensity) for v in value]
    return value


def _compress_dict(data: dict, intensity: str) -> dict:
    """Compress string values in a dict, respecting skip/text key sets."""
    result = {}
    for key, value in data.items():
        if key in _SKIP_KEYS:
            result[key] = value
        elif key in _TEXT_KEYS and isinstance(value, str):
            result[key] = compress_text(value, intensity)
        elif isinstance(value, (dict, list)):
            result[key] = _compress_value(value, intensity)
        else:
            result[key] = value
    return result


def compress_tool_response(
    data: dict[str, Any],
    intensity: str = "full",
) -> dict[str, Any]:
    """Compress an MCP tool response dict.

    Walks the dict tree, compresses text fields, preserves
    structural keys (IDs, paths, kinds, counts).
    """
    if intensity == Intensity.OFF:
        return data
    return _compress_dict(data, intensity)
