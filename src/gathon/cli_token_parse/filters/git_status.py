"""Git status filter — compact porcelain output."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register, run_command

_HINT_RE = re.compile(r'^\s*\(use "git .*"\s*.*\)$')
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

_MAX_FILES = 10
_MAX_UNTRACKED = 8


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*status", "git_status")
def filter_git_status(stdout: str, stderr: str, args: list[str]) -> str:
    has_user_flags = any(
        a for a in args[2:] if a.startswith("-") and a not in ("-C",)
    ) if len(args) > 2 else False

    if has_user_flags:
        return _filter_verbose(stdout)

    out, _, code = run_command("git status --porcelain -b")
    if code != 0:
        return stdout or stderr

    return _parse_porcelain(out)


def _filter_verbose(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = _ANSI_RE.sub("", line)
        if not line.strip():
            continue
        if _HINT_RE.match(line):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n" if lines else "clean — nothing to commit\n"


def _parse_porcelain(text: str) -> str:
    lines = text.strip().splitlines()
    if not lines:
        return "clean — nothing to commit\n"

    parts: list[str] = []
    branch = ""
    staged: list[str] = []
    modified: list[str] = []
    untracked: list[str] = []
    conflicts: list[str] = []

    for line in lines:
        if line.startswith("## "):
            branch = line[3:].split("...")[0]
            parts.append(f"* {branch}")
            continue

        if len(line) < 4:
            continue

        x, y = line[0], line[1]
        name = line[3:].strip()

        if x == "U" or y == "U" or (x == "A" and y == "A") or (x == "D" and y == "D"):
            conflicts.append(name)
        elif x in ("M", "A", "D", "R", "C") and y == " ":
            staged.append(name)
        elif x == " " and y in ("M", "D"):
            modified.append(name)
        elif x in ("M", "A", "D", "R", "C"):
            staged.append(name)
            if y in ("M", "D"):
                modified.append(name)
        elif x == "?" and y == "?":
            untracked.append(name)

    if conflicts:
        parts.append(f"!! Conflicts: {len(conflicts)} files")
        for f in conflicts[:_MAX_FILES]:
            parts.append(f"   {f}")

    if staged:
        parts.append(f"+ Staged: {len(staged)} files")
        for f in staged[:_MAX_FILES]:
            parts.append(f"   {f}")
        if len(staged) > _MAX_FILES:
            parts.append(f"   ... +{len(staged) - _MAX_FILES} more")

    if modified:
        parts.append(f"~ Modified: {len(modified)} files")
        for f in modified[:_MAX_FILES]:
            parts.append(f"   {f}")
        if len(modified) > _MAX_FILES:
            parts.append(f"   ... +{len(modified) - _MAX_FILES} more")

    if untracked:
        parts.append(f"? Untracked: {len(untracked)} files")
        for f in untracked[:_MAX_UNTRACKED]:
            parts.append(f"   {f}")
        if len(untracked) > _MAX_UNTRACKED:
            parts.append(f"   ... +{len(untracked) - _MAX_UNTRACKED} more")

    if not staged and not modified and not untracked and not conflicts:
        if branch:
            parts.append("clean — nothing to commit")
        else:
            return "clean — nothing to commit\n"

    return "\n".join(parts) + "\n"
