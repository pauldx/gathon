"""Git diff filter — compact diff with stat header and hunk truncation."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register, run_command

_STAT_FLAGS = re.compile(r"--(stat|numstat|shortstat|name-only|name-status)")
_DIFF_HEADER_RE = re.compile(r"^diff --git a/(.*) b/")
_HUNK_RE = re.compile(r"^@@\s.*?@@\s*(.*)")

_MAX_HUNK_LINES = 100
_MAX_TOTAL_LINES = 500


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*diff(?:\s|$)", "git_diff")
def filter_git_diff(stdout: str, stderr: str, args: list[str]) -> str:
    if any(_STAT_FLAGS.search(a) for a in args):
        return stdout

    if "--no-compact" in args:
        return stdout

    stat_out, _, _ = run_command("git diff --stat")

    return _compact_diff(stdout, stat_out)


def _compact_diff(diff_text: str, stat_text: str) -> str:
    parts: list[str] = []

    if stat_text.strip():
        parts.append(stat_text.strip())
        parts.append("")

    current_file = ""
    hunk_lines = 0
    total_lines = 0
    adds = 0
    removes = 0
    truncated = False

    for line in diff_text.splitlines():
        if total_lines >= _MAX_TOTAL_LINES:
            truncated = True
            break

        m = _DIFF_HEADER_RE.match(line)
        if m:
            if current_file and (adds or removes):
                parts.append(f"{current_file} (+{adds} -{removes})")
                parts.append("")
            current_file = m.group(1)
            adds = 0
            removes = 0
            hunk_lines = 0
            continue

        if line.startswith("index ") or line.startswith("--- ") or line.startswith("+++ "):
            continue

        hm = _HUNK_RE.match(line)
        if hm:
            hunk_lines = 0
            ctx = hm.group(1).strip()
            if ctx:
                parts.append(f"  @@ {ctx}")
            else:
                parts.append(f"  {line.strip()}")
            total_lines += 1
            continue

        if line.startswith("+") or line.startswith("-") or line.startswith(" "):
            if hunk_lines < _MAX_HUNK_LINES:
                parts.append(f"  {line}")
                total_lines += 1
            hunk_lines += 1

            if line.startswith("+"):
                adds += 1
            elif line.startswith("-"):
                removes += 1

    if current_file and (adds or removes):
        parts.append(f"{current_file} (+{adds} -{removes})")

    if truncated:
        parts.append(f"\n... truncated ({_MAX_TOTAL_LINES} lines shown)")

    if not parts:
        return "No diff.\n"

    return "\n".join(parts) + "\n"
