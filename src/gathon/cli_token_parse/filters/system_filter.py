"""System filters — find, tree, env, json, log dedup, wc, diff, deps."""

from __future__ import annotations

import json
import re
from collections import Counter

from gathon.cli_token_parse.engine import register

_MAX_RESULTS = 200
_MAX_LOG_LINES = 100
_NOISE_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".mypy_cache",
    "target", "dist", "build", ".next", ".tox", ".venv",
})


@register(r"^find\s+", "find")
def filter_find(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if not lines:
        return "0 results\n"

    filtered = [
        ln for ln in lines
        if not any(nd in ln for nd in _NOISE_DIRS)
    ]

    if len(filtered) <= _MAX_RESULTS:
        parts = [f"{len(filtered)} results"]
        parts.extend(filtered)
        return "\n".join(parts) + "\n"

    by_ext: Counter[str] = Counter()
    for f in filtered:
        ext = f.rsplit(".", 1)[-1] if "." in f else ""
        if ext and len(ext) <= 6:
            by_ext[f".{ext}"] += 1

    parts = [f"{len(filtered)} results (showing {_MAX_RESULTS})"]
    parts.extend(filtered[:_MAX_RESULTS])
    parts.append(f"\n... +{len(filtered) - _MAX_RESULTS} more")
    if by_ext:
        top = ", ".join(f"{e} ({c})" for e, c in by_ext.most_common(5))
        parts.append(f"Extensions: {top}")
    return "\n".join(parts) + "\n"


@register(r"^tree(?:\s|$)", "tree")
def filter_tree(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    filtered = [
        ln for ln in lines
        if not any(nd in ln for nd in _NOISE_DIRS)
    ]
    summary = ""
    if filtered and re.match(r"^\d+\s+director", filtered[-1]):
        summary = filtered.pop()

    if len(filtered) > 100:
        result = filtered[:80]
        result.append(f"\n... +{len(filtered) - 80} more entries")
        if summary:
            result.append(summary)
        return "\n".join(result) + "\n"

    if summary:
        filtered.append(summary)
    return "\n".join(filtered) + "\n"


@register(r"^env(?:\s|$)", "env")
def filter_env(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    safe_lines: list[str] = []
    sensitive = {"SECRET", "KEY", "TOKEN", "PASSWORD", "CREDENTIAL", "AUTH"}

    for line in sorted(lines):
        if "=" not in line:
            continue
        key = line.split("=", 1)[0]
        if any(s in key.upper() for s in sensitive):
            safe_lines.append(f"{key}=***")
        else:
            val = line.split("=", 1)[1]
            if len(val) > 60:
                val = val[:57] + "..."
            safe_lines.append(f"{key}={val}")

    parts = [f"ENV: {len(safe_lines)} variables"]
    parts.extend(safe_lines[:40])
    if len(safe_lines) > 40:
        parts.append(f"... +{len(safe_lines) - 40} more")
    return "\n".join(parts) + "\n"


@register(r"^(?:jq|python3?\s+-m\s+json\.tool)\s+", "json_structure")
def filter_json(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        structure = _json_structure(data)
        return json.dumps(structure, indent=2) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout


def _json_structure(obj: object, depth: int = 0) -> object:
    if depth > 3:
        return "..."
    if isinstance(obj, dict):
        return {k: _json_structure(v, depth + 1) for k, v in list(obj.items())[:10]}
    if isinstance(obj, list):
        if not obj:
            return []
        return [_json_structure(obj[0], depth + 1), f"... ({len(obj)} items)"]
    if isinstance(obj, str):
        return f"str({len(obj)})"
    if isinstance(obj, (int, float)):
        return type(obj).__name__
    if isinstance(obj, bool):
        return "bool"
    if obj is None:
        return "null"
    return str(type(obj).__name__)


@register(r"^(?:tail\s+-f|journalctl)\s+", "log_dedup")
def filter_log(stdout: str, stderr: str, args: list[str]) -> str:
    lines = (stdout + stderr).splitlines()
    if len(lines) <= _MAX_LOG_LINES:
        return stdout + stderr

    seen: dict[str, int] = {}
    deduped: list[str] = []

    for line in lines:
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "TIMESTAMP", line)
        normalized = re.sub(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IP", normalized)
        if normalized in seen:
            seen[normalized] += 1
        else:
            seen[normalized] = 1
            deduped.append(line)

    dupes = sum(v - 1 for v in seen.values() if v > 1)
    result = deduped[-_MAX_LOG_LINES:]
    if dupes:
        result.append(f"\n({dupes} duplicate lines collapsed)")
    return "\n".join(result) + "\n"


@register(r"^wc(?:\s|$)", "wc")
def filter_wc(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if len(lines) <= 20:
        return stdout
    return "\n".join(lines[:15]) + f"\n... +{len(lines) - 15} more\n" + lines[-1] + "\n"


@register(r"^diff\s+", "diff")
def filter_diff(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.splitlines()
    if len(lines) <= 100:
        return stdout
    return "\n".join(lines[:80]) + f"\n\n... ({len(lines) - 80} lines truncated)\n"


@register(r"^(?:bundle\s+install|gem\s+install)", "bundle_install")
def filter_bundle_install(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [ln for ln in combined.splitlines() if not ln.startswith("Using ") and ln.strip()]
    if not lines:
        return "ok\n"
    return "\n".join(lines[:15]) + "\n"
