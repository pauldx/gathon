"""Git log filter — one-line compact format with body truncation."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register, run_command

_FORMAT_FLAGS = re.compile(r"--(pretty|format|oneline)", re.IGNORECASE)
_LIMIT_FLAGS = re.compile(r"^-(\d+)$|^-n\s*(\d+)$|^--max-count[=\s]", re.IGNORECASE)
_BODY_KEEP = re.compile(
    r"BREAKING|Closes?\s+#|Fixes?\s+#|Refs?\s+#|design|migration|deprecat",
    re.IGNORECASE,
)

_DEFAULT_LIMIT = 10
_DEFAULT_WIDTH = 80
_USER_WIDTH = 120
_MAX_BODY_LINES = 3
_END_MARKER = "---END---"
_CTP_FORMAT = f"%h %s (%ar) <%an>%n%b%n{_END_MARKER}"


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*log(?:\s|$)", "git_log")
def filter_git_log(stdout: str, stderr: str, args: list[str]) -> str:
    has_format = any(_FORMAT_FLAGS.search(a) for a in args)
    has_limit = any(_LIMIT_FLAGS.search(a) for a in args)

    if has_format and has_limit:
        return _truncate_lines(stdout, _USER_WIDTH)

    cmd_parts = ["git", "log"]
    extra_args = [a for a in args[2:] if a != "log"]

    if not has_format:
        cmd_parts.append(f"--pretty=format:{_CTP_FORMAT}")
    else:
        cmd_parts.extend(a for a in extra_args if _FORMAT_FLAGS.search(a))
        extra_args = [a for a in extra_args if not _FORMAT_FLAGS.search(a)]

    if not has_limit:
        cmd_parts.append(f"-{_DEFAULT_LIMIT}")

    if "--no-merges" not in args and "--merges" not in args:
        cmd_parts.append("--no-merges")

    remaining = [a for a in extra_args if not _LIMIT_FLAGS.search(a)]
    cmd_parts.extend(remaining)

    out, err, code = run_command(" ".join(cmd_parts))
    if code != 0:
        return stdout or stderr or out or err

    if has_format:
        return _truncate_lines(out, _USER_WIDTH if has_limit else _DEFAULT_WIDTH)

    return _parse_commits(out)


def _truncate_lines(text: str, width: int) -> str:
    lines = []
    for line in text.splitlines():
        if len(line) > width:
            lines.append(line[:width - 3] + "...")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def _parse_commits(text: str) -> str:
    blocks = text.split(_END_MARKER)
    result: list[str] = []

    for block in blocks:
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if not lines:
            continue

        header = lines[0]
        if len(header) > _DEFAULT_WIDTH:
            header = header[:_DEFAULT_WIDTH - 3] + "..."
        result.append(header)

        body_lines = lines[1:]
        kept = []
        for bl in body_lines:
            bl = bl.strip()
            if not bl:
                continue
            if _BODY_KEEP.search(bl):
                if len(bl) > _DEFAULT_WIDTH:
                    bl = bl[:_DEFAULT_WIDTH - 3] + "..."
                kept.append(f"  {bl}")
                if len(kept) >= _MAX_BODY_LINES:
                    break

        omitted = len(body_lines) - len(kept)
        result.extend(kept)
        if omitted > 0 and kept:
            result.append(f"  [+{omitted} lines omitted]")
        if kept:
            result.append("")

    return "\n".join(result) + "\n" if result else "No commits found.\n"
