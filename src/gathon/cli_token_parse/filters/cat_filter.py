"""Cat/read filter — smart truncation for large files."""

from __future__ import annotations

from gathon.cli_token_parse.engine import register

_MAX_LINES = 200
_HEAD_LINES = 50
_TAIL_LINES = 50


@register(r"^(?:cat|head|tail)(?:\s|$)", "cat")
def filter_cat(stdout: str, stderr: str, args: list[str]) -> str:
    if not stdout:
        return stderr or "(empty)\n"

    lines = stdout.splitlines()
    total = len(lines)

    if total <= _MAX_LINES:
        return stdout

    head = lines[:_HEAD_LINES]
    tail = lines[-_TAIL_LINES:]
    omitted = total - _HEAD_LINES - _TAIL_LINES

    parts = head + [f"\n... ({omitted} lines omitted) ...\n"] + tail
    return "\n".join(parts) + "\n"
