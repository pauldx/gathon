"""Event types and extraction logic for session continuity."""

from __future__ import annotations

import re
from typing import Any

from gathon.session.db import SessionEvent

# -- Priority 1: Critical (always capture) --
P1_CRITICAL = 1
# -- Priority 2: High --
P2_HIGH = 2
# -- Priority 3: Normal --
P3_NORMAL = 3

EVENT_REGISTRY: dict[str, dict[str, Any]] = {
    # P1 — Critical
    "file_read":      {"priority": P1_CRITICAL, "category": "files"},
    "file_edit":      {"priority": P1_CRITICAL, "category": "files"},
    "file_write":     {"priority": P1_CRITICAL, "category": "files"},
    "task_create":    {"priority": P1_CRITICAL, "category": "tasks"},
    "task_update":    {"priority": P1_CRITICAL, "category": "tasks"},
    "task_complete":  {"priority": P1_CRITICAL, "category": "tasks"},
    "user_prompt":    {"priority": P1_CRITICAL, "category": "context"},
    "plan_enter":     {"priority": P1_CRITICAL, "category": "context"},
    "plan_exit":      {"priority": P1_CRITICAL, "category": "context"},
    # P2 — High
    "git_commit":     {"priority": P2_HIGH, "category": "git"},
    "git_checkout":   {"priority": P2_HIGH, "category": "git"},
    "git_merge":      {"priority": P2_HIGH, "category": "git"},
    "git_push":       {"priority": P2_HIGH, "category": "git"},
    "git_pull":       {"priority": P2_HIGH, "category": "git"},
    "git_diff":       {"priority": P2_HIGH, "category": "git"},
    "git_status":     {"priority": P2_HIGH, "category": "git"},
    "error":          {"priority": P2_HIGH, "category": "errors"},
    "error_fix":      {"priority": P2_HIGH, "category": "errors"},
    "constraint":     {"priority": P2_HIGH, "category": "context"},
    "blocker":        {"priority": P2_HIGH, "category": "context"},
    # P3 — Normal
    "mcp_tool_use":   {"priority": P3_NORMAL, "category": "tools"},
    "subagent_complete": {"priority": P3_NORMAL, "category": "tools"},
    "env_change":     {"priority": P3_NORMAL, "category": "environment"},
}

_GIT_CMD_PATTERNS: list[tuple[str, str]] = [
    (r"^git\s+commit\b", "git_commit"),
    (r"^git\s+checkout\b", "git_checkout"),
    (r"^git\s+merge\b", "git_merge"),
    (r"^git\s+push\b", "git_push"),
    (r"^git\s+pull\b", "git_pull"),
    (r"^git\s+diff\b", "git_diff"),
    (r"^git\s+status\b", "git_status"),
]

_READ_CMD_PATTERNS = re.compile(
    r"^(cat|less|head|tail|bat|more)\s+"
)


def _make_event(event_type: str, data: dict[str, Any], source_tool: str = "") -> SessionEvent:
    info = EVENT_REGISTRY.get(event_type, {"priority": P3_NORMAL, "category": "general"})
    return SessionEvent(
        event_type=event_type,
        priority=info["priority"],
        category=info["category"],
        data=data,
        source_tool=source_tool,
    )


def extract_from_bash(
    command: str,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> list[SessionEvent]:
    events: list[SessionEvent] = []
    cmd = command.strip()

    if exit_code != 0:
        events.append(_make_event("error", {
            "command": cmd[:200],
            "exit_code": exit_code,
            "stderr": stderr[:500] if stderr else "",
        }, source_tool="Bash"))

    for pattern, event_type in _GIT_CMD_PATTERNS:
        if re.match(pattern, cmd):
            data = _extract_git_data(event_type, cmd, stdout)
            events.append(_make_event(event_type, data, source_tool="Bash"))
            return events

    if _READ_CMD_PATTERNS.match(cmd):
        parts = cmd.split(maxsplit=1)
        file_path = parts[1].strip().strip("'\"") if len(parts) > 1 else ""
        events.append(_make_event("file_read", {
            "file_path": file_path,
        }, source_tool="Bash"))

    return events


def _extract_git_data(event_type: str, cmd: str, stdout: str) -> dict[str, Any]:
    if event_type == "git_commit":
        hash_match = re.search(r"\[[\w/]+\s+([a-f0-9]{7,})\]", stdout)
        msg_match = re.search(r"\]\s+(.+)", stdout)
        return {
            "hash": hash_match.group(1) if hash_match else "",
            "message": msg_match.group(1)[:200] if msg_match else "",
            "command": cmd[:200],
        }
    if event_type == "git_checkout":
        branch_match = re.search(r"(?:checkout|switch)\s+(?:-b\s+)?(\S+)", cmd)
        return {
            "branch": branch_match.group(1) if branch_match else "",
        }
    if event_type == "git_merge":
        branch_match = re.search(r"merge\s+(\S+)", cmd)
        return {
            "branch": branch_match.group(1) if branch_match else "",
            "result": "conflict" if "CONFLICT" in stdout else "clean",
        }
    if event_type == "git_push":
        remote_match = re.search(r"push\s+(\S+)(?:\s+(\S+))?", cmd)
        return {
            "remote": remote_match.group(1) if remote_match else "origin",
            "branch": remote_match.group(2) if remote_match and remote_match.group(2) else "",
        }
    if event_type == "git_pull":
        remote_match = re.search(r"pull\s+(\S+)(?:\s+(\S+))?", cmd)
        return {
            "remote": remote_match.group(1) if remote_match else "origin",
            "branch": remote_match.group(2) if remote_match and remote_match.group(2) else "",
        }
    if event_type == "git_diff":
        insertions = len(re.findall(r"^\+", stdout, re.MULTILINE))
        deletions = len(re.findall(r"^-", stdout, re.MULTILINE))
        files = set(re.findall(r"^diff --git a/(\S+)", stdout, re.MULTILINE))
        return {
            "file_count": len(files),
            "insertions": insertions,
            "deletions": deletions,
        }
    if event_type == "git_status":
        modified = len(re.findall(r"^\s*M\s", stdout, re.MULTILINE))
        added = len(re.findall(r"^\s*A\s", stdout, re.MULTILINE))
        deleted = len(re.findall(r"^\s*D\s", stdout, re.MULTILINE))
        untracked = len(re.findall(r"^\?\?\s", stdout, re.MULTILINE))
        return {
            "modified": modified,
            "added": added,
            "deleted": deleted,
            "untracked": untracked,
        }
    return {"command": cmd[:200]}


def extract_from_edit(
    file_path: str,
    old_content: str,
    new_content: str,
) -> SessionEvent:
    old_lines = old_content.count("\n")
    new_lines = new_content.count("\n")
    diff = new_lines - old_lines
    return _make_event("file_edit", {
        "file_path": file_path,
        "lines_changed": abs(diff),
        "lines_added": max(diff, 0),
        "lines_removed": abs(min(diff, 0)),
    }, source_tool="Edit")


def extract_from_write(file_path: str, content: str) -> SessionEvent:
    return _make_event("file_write", {
        "file_path": file_path,
        "size_bytes": len(content.encode("utf-8")),
    }, source_tool="Write")


def extract_from_read(file_path: str) -> SessionEvent:
    return _make_event("file_read", {
        "file_path": file_path,
    }, source_tool="Read")


def extract_from_tool_use(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
) -> list[SessionEvent]:
    events: list[SessionEvent] = []

    if tool_name == "Bash":
        command = tool_input.get("command", "")
        stdout = tool_output.get("stdout", "")
        stderr = tool_output.get("stderr", "")
        exit_code = tool_output.get("exit_code", 0)
        events.extend(extract_from_bash(command, stdout, stderr, exit_code))
    elif tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        events.append(extract_from_edit(file_path, old, new))
    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        content = tool_input.get("content", "")
        events.append(extract_from_write(file_path, content))
    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        events.append(extract_from_read(file_path))
    elif tool_name == "TodoWrite":
        todos = tool_input.get("todos", [])
        for todo in todos:
            status = (todo.get("status", "") or "").lower()
            if status == "completed":
                events.append(_make_event("task_complete", {
                    "id": todo.get("id", ""),
                    "subject": todo.get("content", "")[:200],
                }, source_tool="TodoWrite"))
            elif status == "in_progress":
                events.append(_make_event("task_update", {
                    "id": todo.get("id", ""),
                    "status": status,
                    "subject": todo.get("content", "")[:200],
                }, source_tool="TodoWrite"))
            else:
                events.append(_make_event("task_create", {
                    "id": todo.get("id", ""),
                    "subject": todo.get("content", "")[:200],
                    "status": status,
                }, source_tool="TodoWrite"))

    events.append(_make_event("mcp_tool_use", {
        "tool_name": tool_name,
    }, source_tool=tool_name))

    return events
