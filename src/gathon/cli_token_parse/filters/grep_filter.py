"""Grep/rg filter — group matches by file, truncate long lines."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register

_MATCH_RE = re.compile(r"^(.+?):(\d+):(.*)$")

_MAX_PER_FILE = 10
_MAX_TOTAL = 200
_MAX_LINE_LEN = 100
_MAX_PATH_LEN = 50


@register(r"^(?:grep|rg|ripgrep)(?:\s|$)", "grep")
def filter_grep(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.splitlines()
    if not lines:
        pattern = _extract_pattern(args)
        return f"0 matches for '{pattern}'\n"

    by_file: dict[str, list[tuple[int, str]]] = {}
    total = 0

    for line in lines:
        m = _MATCH_RE.match(line)
        if not m:
            continue
        fpath, lineno, content = m.group(1), int(m.group(2)), m.group(3)
        by_file.setdefault(fpath, []).append((lineno, content.strip()))
        total += 1

    if total == 0:
        return stdout

    file_count = len(by_file)
    parts = [f"{total} matches in {file_count}F:"]
    parts.append("")

    shown = 0
    files_shown = 0
    for fpath, matches in by_file.items():
        if shown >= _MAX_TOTAL:
            remaining_files = file_count - files_shown
            parts.append(f"\n... +{remaining_files} files")
            break

        compact_path = _compact_path(fpath)
        parts.append(f"[file] {compact_path} ({len(matches)}):")

        for lineno, content in matches[:_MAX_PER_FILE]:
            truncated = _truncate_match(content, _MAX_LINE_LEN)
            parts.append(f"   {lineno}: {truncated}")
            shown += 1

        remaining = len(matches) - _MAX_PER_FILE
        if remaining > 0:
            parts.append(f"   +{remaining}")

        parts.append("")
        files_shown += 1

    if shown >= _MAX_TOTAL:
        parts.append(f"... +{total - shown}")

    return "\n".join(parts) + "\n"


def _extract_pattern(args: list[str]) -> str:
    skip_next = False
    for a in args[1:]:
        if skip_next:
            skip_next = False
            continue
        if a.startswith("-") and not a.startswith("--"):
            if "e" in a:
                skip_next = True
            continue
        if a.startswith("--"):
            if "=" in a:
                continue
            skip_next = True
            continue
        return a
    return "?"


def _compact_path(path: str) -> str:
    if len(path) <= _MAX_PATH_LEN:
        return path
    parts = path.split("/")
    if len(parts) <= 3:
        return path
    return f"{parts[0]}/.../{parts[-2]}/{parts[-1]}"


def _truncate_match(line: str, max_len: int) -> str:
    if len(line) <= max_len:
        return line
    return line[:max_len - 3] + "..."
