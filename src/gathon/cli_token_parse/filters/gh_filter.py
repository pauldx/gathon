"""GitHub CLI filter — compact pr/issue/run listings."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register

_MAX_ITEMS = 20
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_BADGE_RE = re.compile(r"!\[.*?\]\(.*?\)")
_PR_LINE_RE = re.compile(r"#(\d+)\s+(.+?)\s+(\S+)\s+(OPEN|CLOSED|MERGED)\s+(.+)")
_ISSUE_LINE_RE = re.compile(r"#(\d+)\s+(.+?)\s+(OPEN|CLOSED)\s+(.+)")
_RUN_LINE_RE = re.compile(r"(\S+)\s+(\w+)\s+(.+?)\s+(\d+)\s")


@register(r"^gh\s+pr\s+list", "gh_pr_list")
def filter_gh_pr_list(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if not lines:
        return "No PRs found.\n"
    parts = [f"PRs ({min(len(lines), _MAX_ITEMS)} shown):"]
    for line in lines[:_MAX_ITEMS]:
        m = _PR_LINE_RE.match(line)
        if m:
            num, title, branch, state, date = m.groups()
            icon = {"OPEN": "O", "MERGED": "M", "CLOSED": "C"}.get(state, "?")
            parts.append(f"  [{icon}] #{num} {title[:60]}")
        else:
            parts.append(f"  {line[:80]}")
    if len(lines) > _MAX_ITEMS:
        parts.append(f"  ... +{len(lines) - _MAX_ITEMS} more")
    return "\n".join(parts) + "\n"


@register(r"^gh\s+pr\s+view", "gh_pr_view")
def filter_gh_pr_view(stdout: str, stderr: str, args: list[str]) -> str:
    text = _HTML_COMMENT_RE.sub("", stdout)
    text = _BADGE_RE.sub("", text)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[:30]) + "\n"


@register(r"^gh\s+issue\s+list", "gh_issue_list")
def filter_gh_issue_list(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if not lines:
        return "No issues found.\n"
    parts = [f"Issues ({min(len(lines), _MAX_ITEMS)} shown):"]
    for line in lines[:_MAX_ITEMS]:
        m = _ISSUE_LINE_RE.match(line)
        if m:
            num, title, state, date = m.groups()
            parts.append(f"  [{state.lower()}] #{num} {title[:60]}")
        else:
            parts.append(f"  {line[:80]}")
    return "\n".join(parts) + "\n"


@register(r"^gh\s+issue\s+view", "gh_issue_view")
def filter_gh_issue_view(stdout: str, stderr: str, args: list[str]) -> str:
    text = _HTML_COMMENT_RE.sub("", stdout)
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[:30]) + "\n"


@register(r"^gh\s+run\s+list", "gh_run_list")
def filter_gh_run_list(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if not lines:
        return "No workflow runs.\n"
    parts = ["Workflow Runs:"]
    for line in lines[:_MAX_ITEMS]:
        parts.append(f"  {line[:80]}")
    return "\n".join(parts) + "\n"
