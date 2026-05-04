"""Git operations filter — compact add/commit/push to 'ok' format."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register, run_command

_COMMIT_HASH_RE = re.compile(r"\[[\w/.-]+\s+([a-f0-9]{7,})\]")
_SHORTSTAT_RE = re.compile(
    r"(\d+)\s+files?\s+changed(?:,\s+(\d+)\s+insertion)?(?:,\s+(\d+)\s+deletion)?",
)


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*add(?:\s|$)", "git_add")
def filter_git_add(stdout: str, stderr: str, args: list[str]) -> str:
    stat_out, _, _ = run_command("git diff --cached --shortstat")
    stat = stat_out.strip()
    if stat:
        return f"ok {stat}\n"
    return "ok (nothing to add)\n"


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*commit(?:\s|$)", "git_commit")
def filter_git_commit(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    m = _COMMIT_HASH_RE.search(combined)
    if m:
        return f"ok {m.group(1)[:7]}\n"

    if "nothing to commit" in combined.lower():
        return "ok (nothing to commit)\n"

    return combined


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*push(?:\s|$)", "git_push")
def filter_git_push(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    if "Everything up-to-date" in combined or "up-to-date" in combined.lower():
        return "ok (up-to-date)\n"

    for line in combined.splitlines():
        if "->" in line and ".." in line:
            parts = line.strip().split()
            for p in parts:
                if "->" in p or ".." in p:
                    continue
                if "/" in p:
                    return f"ok -> {p}\n"

    if "error" in combined.lower() or "fatal" in combined.lower():
        return combined

    return "ok\n"


@register(r"^(?:git|yadm)\s+(?:-[Cc]\s+\S+\s+)*pull(?:\s|$)", "git_pull")
def filter_git_pull(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    if "Already up to date" in combined or "Already up-to-date" in combined:
        return "ok (up-to-date)\n"

    files_changed = 0
    insertions = 0
    deletions = 0
    m = _SHORTSTAT_RE.search(combined)
    if m:
        files_changed = int(m.group(1))
        insertions = int(m.group(2) or 0)
        deletions = int(m.group(3) or 0)
        return f"ok {files_changed} files +{insertions} -{deletions}\n"

    return combined
