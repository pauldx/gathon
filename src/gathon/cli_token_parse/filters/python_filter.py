"""Python tool filters — ruff, mypy, pip."""

from __future__ import annotations

import json
import re
from collections import Counter

from gathon.cli_token_parse.engine import register

_MYPY_ERR_RE = re.compile(r"^(.+?):(\d+):\s*(error|warning|note):\s*(.+?)(?:\s+\[(.+?)\])?$")
_MAX_FILES = 10


@register(r"^(?:python3?\s+-m\s+)?ruff\s+check", "ruff_check")
def filter_ruff(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        if not data:
            return "Ruff: clean\n"
        total = len(data)
        fixable = sum(1 for d in data if d.get("fix"))
        by_rule: Counter[str] = Counter()
        by_file: Counter[str] = Counter()
        for d in data:
            by_rule[d.get("code", "?")] += 1
            by_file[d.get("filename", "?")] += 1

        parts = [f"Ruff: {total} issues ({fixable} fixable)"]
        parts.append("Top rules:")
        for rule, cnt in by_rule.most_common(5):
            parts.append(f"  {rule} ({cnt}x)")
        parts.append("Top files:")
        for fp, cnt in by_file.most_common(_MAX_FILES):
            parts.append(f"  {fp} ({cnt})")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass

    lines = (stdout + stderr).strip().splitlines()
    if not lines:
        return "Ruff: clean\n"
    count = sum(1 for ln in lines if re.match(r".+:\d+:\d+:", ln))
    return f"Ruff: {count} issues\n" + "\n".join(lines[:20]) + "\n"


@register(r"^(?:python3?\s+-m\s+)?mypy(?:\s|$)", "mypy")
def filter_mypy(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = combined.strip().splitlines()

    by_file: dict[str, list[str]] = {}
    by_code: Counter[str] = Counter()
    total = 0

    for line in lines:
        m = _MYPY_ERR_RE.match(line)
        if m:
            fp, lineno, severity, msg, code = m.groups()
            if severity == "error":
                total += 1
                by_file.setdefault(fp, []).append(f"  L{lineno}: [{code or '?'}] {msg[:80]}")
                if code:
                    by_code[code] += 1

    if total == 0:
        return "mypy: clean\n"

    parts = [f"mypy: {total} errors in {len(by_file)} files"]
    if by_code:
        top = ", ".join(f"{c} ({n}x)" for c, n in by_code.most_common(5))
        parts.append(f"Top codes: {top}")
    for fp, errs in sorted(by_file.items(), key=lambda x: -len(x[1]))[:_MAX_FILES]:
        parts.append(f"\n{fp} ({len(errs)} errors)")
        for e in errs[:5]:
            parts.append(e)
        if len(errs) > 5:
            parts.append(f"  ... +{len(errs) - 5} more")
    return "\n".join(parts) + "\n"


@register(r"^(?:python3?\s+-m\s+)?pip\s+list", "pip_list")
def filter_pip_list(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        if not data:
            return "pip list: 0 packages\n"
        parts = [f"pip list: {len(data)} packages"]
        for pkg in data[:30]:
            parts.append(f"  {pkg.get('name', '?')} ({pkg.get('version', '?')})")
        if len(data) > 30:
            parts.append(f"  ... +{len(data) - 30} more")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass

    lines = stdout.strip().splitlines()
    count = max(0, len(lines) - 2)
    return f"pip list: {count} packages\n" + "\n".join(lines[:32]) + "\n"


@register(r"^(?:python3?\s+-m\s+)?pip\s+.*outdated", "pip_outdated")
def filter_pip_outdated(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        if not data:
            return "pip outdated: all up-to-date\n"
        parts = [f"pip outdated: {len(data)} packages"]
        for i, pkg in enumerate(data[:20], 1):
            name = pkg.get("name", "?")
            cur = pkg.get("version", "?")
            latest = pkg.get("latest_version", "?")
            parts.append(f"  {i}. {name} ({cur} → {latest})")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout
