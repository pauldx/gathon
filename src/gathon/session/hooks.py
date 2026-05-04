"""Hook integration for Claude Code's hook protocol."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from gathon.session.db import SessionDB
from gathon.session.events import extract_from_tool_use
from gathon.session.snapshot import SnapshotBuilder, build_session_guide

_DENY_PATTERNS: list[str] = [
    "rm -rf /",
    "rm -rf ~",
    "mkfs.",
    ":(){:|:&};:",
    "dd if=/dev/zero of=/dev/",
]

_SESSION_FILE = Path.home() / ".gathon" / "sessions" / "current_session.txt"


def _get_session_id() -> str:
    if _SESSION_FILE.exists():
        content = _SESSION_FILE.read_text().strip()
        if content:
            return content
    return _create_session_id()


def _create_session_id() -> str:
    import secrets
    from datetime import datetime
    session_id = datetime.now().strftime("%Y%m%d") + "_" + secrets.token_hex(3)
    _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    _SESSION_FILE.write_text(session_id)
    return session_id


def _get_project_dir() -> str:
    return os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())


def _get_db() -> SessionDB:
    return SessionDB(project_dir=_get_project_dir())


def handle_pre_tool_use(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    if tool_name == "Bash":
        command = tool_input.get("command", "")
        for pattern in _DENY_PATTERNS:
            if pattern in command:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Blocked dangerous pattern: {pattern}",
                    }
                }

        if _is_curl_or_wget(command):
            return {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow",
                    "permissionDecisionReason": (
                        "Suggestion: consider using ctx_fetch_and_index "
                        "to capture this URL into the knowledge graph."
                    ),
                }
            }

    return None


def handle_post_tool_use(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_output: dict[str, Any],
    session_id: str | None = None,
) -> None:
    sid = session_id or _get_session_id()
    db = _get_db()
    try:
        events = extract_from_tool_use(tool_name, tool_input, tool_output)
        for event in events:
            db.log_event(
                session_id=sid,
                event_type=event.event_type,
                priority=event.priority,
                category=event.category,
                data=event.data,
                source_tool=event.source_tool,
            )
    finally:
        db.close()


def handle_pre_compact(session_id: str | None = None) -> str:
    sid = session_id or _get_session_id()
    db = _get_db()
    try:
        builder = SnapshotBuilder(db, sid)
        snapshot = builder.build()
        db.save_snapshot(sid, snapshot)
        return snapshot
    finally:
        db.close()


def handle_session_start(session_id: str | None = None) -> str:
    sid = session_id or _get_session_id()
    db = _get_db()
    try:
        existing = db.get_latest_snapshot(sid)
        if existing:
            guide = build_session_guide(db, sid)
            return guide

        events = db.get_events(sid)
        if events:
            guide = build_session_guide(db, sid)
            return guide

        return (
            "<session-guide>\n"
            f"  <session-id>{sid}</session-id>\n"
            "  <status>new</status>\n"
            "</session-guide>\n"
        )
    finally:
        db.close()


def pre_tool_use_hook() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})

        result = handle_pre_tool_use(tool_name, tool_input)
        if result:
            print(json.dumps(result))
    except Exception:
        pass


def post_tool_use_hook() -> None:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        tool_name = data.get("tool_name", "")
        tool_input = data.get("tool_input", {})
        tool_output = data.get("tool_output", {})

        handle_post_tool_use(tool_name, tool_input, tool_output)
    except Exception:
        pass


def pre_compact_hook() -> None:
    try:
        snapshot = handle_pre_compact()
        print(snapshot)
    except Exception:
        pass


def session_start_hook() -> None:
    try:
        guide = handle_session_start()
        print(guide)
    except Exception:
        pass


def _is_curl_or_wget(command: str) -> bool:
    cmd = command.strip()
    return cmd.startswith("curl ") or cmd.startswith("wget ")
