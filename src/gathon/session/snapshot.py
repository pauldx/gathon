"""Priority-tiered snapshot builder for context compaction survival."""

from __future__ import annotations

from gathon.session.db import SessionDB, SessionEvent
from gathon.session.events import P1_CRITICAL, P2_HIGH, P3_NORMAL


class SnapshotBuilder:
    """Builds priority-tiered XML snapshots from session events."""

    def __init__(self, db: SessionDB, session_id: str, max_bytes: int = 2048) -> None:
        self._db = db
        self._session_id = session_id
        self._max_bytes = max_bytes

    def build(self) -> str:
        return build_snapshot(self._db, self._session_id, self._max_bytes)


def build_snapshot(db: SessionDB, session_id: str, max_bytes: int = 2048) -> str:
    p1_events = db.get_events(session_id, priority_max=P1_CRITICAL)
    p2_events = db.get_events(session_id, priority_max=P2_HIGH)
    p3_events = db.get_events(session_id, priority_max=P3_NORMAL)

    p2_only = [e for e in p2_events if e.priority == P2_HIGH]
    p3_only = [e for e in p3_events if e.priority == P3_NORMAL]

    sections: list[str] = []

    prompt_section = _build_prompt_section(p1_events)
    if prompt_section:
        sections.append(prompt_section)

    tasks_section = _build_tasks_section(p1_events)
    if tasks_section:
        sections.append(tasks_section)

    errors_section = _build_errors_section(p2_only)
    if errors_section:
        sections.append(errors_section)

    files_section = _build_files_section(p1_events)
    if files_section:
        sections.append(files_section)

    git_section = _build_git_section(p2_only)
    if git_section:
        sections.append(git_section)

    context_section = _build_context_section(p1_events, p2_only)
    if context_section:
        sections.append(context_section)

    tools_section = _build_tools_section(p3_only)
    if tools_section:
        sections.append(tools_section)

    snapshot = "<session-snapshot>\n"
    remaining = max_bytes - len(snapshot) - len("</session-snapshot>\n")

    for section in sections:
        encoded_len = len(section.encode("utf-8"))
        if encoded_len <= remaining:
            snapshot += section
            remaining -= encoded_len
        else:
            truncated = _truncate_section(section, remaining)
            if truncated:
                snapshot += truncated
            break

    snapshot += "</session-snapshot>\n"
    return snapshot


def build_session_guide(db: SessionDB, session_id: str) -> str:
    existing_snapshot = db.get_latest_snapshot(session_id)
    events = db.get_events(session_id)
    counts = db.get_event_counts(session_id)

    lines: list[str] = ["<session-guide>"]

    last_prompt = _find_last_event(events, "user_prompt")
    if last_prompt:
        prompt_text = last_prompt.data.get("text", "")[:500]
        lines.append(f"  <last-prompt>{_escape_xml(prompt_text)}</last-prompt>")

    task_events = [e for e in events if e.category == "tasks"]
    if task_events:
        lines.append("  <task-checklist>")
        seen: set[str] = set()
        for e in reversed(task_events):
            task_id = e.data.get("id", "")
            if task_id in seen:
                continue
            seen.add(task_id)
            subject = e.data.get("subject", "")[:100]
            status = "done" if e.event_type == "task_complete" else e.data.get("status", "pending")
            lines.append(f'    <task status="{status}">{_escape_xml(subject)}</task>')
        lines.append("  </task-checklist>")

    error_events = [e for e in events if e.event_type == "error"]
    fix_events = {
        e.data.get("original_error", ""): e
        for e in events if e.event_type == "error_fix"
    }
    unresolved = [e for e in error_events if e.data.get("stderr", "") not in fix_events]
    if unresolved:
        lines.append("  <unresolved-errors>")
        for e in unresolved[-5:]:
            tool = e.source_tool
            msg = e.data.get("stderr", e.data.get("command", ""))[:200]
            lines.append(f'    <error tool="{tool}">{_escape_xml(msg)}</error>')
        lines.append("  </unresolved-errors>")

    file_events = [
        e for e in events
        if e.category == "files" and e.event_type in ("file_edit", "file_write")
    ]
    if file_events:
        lines.append("  <files-modified>")
        seen_files: set[str] = set()
        for e in reversed(file_events):
            fp = e.data.get("file_path", "")
            if fp in seen_files:
                continue
            seen_files.add(fp)
            if e.event_type == "file_write":
                size = e.data.get("size_bytes", 0)
                lines.append(f"    <file>{_escape_xml(fp)} (created, {size}B)</file>")
            else:
                added = e.data.get("lines_added", 0)
                removed = e.data.get("lines_removed", 0)
                lines.append(f"    <file>{_escape_xml(fp)} (edited, +{added}/-{removed})</file>")
        lines.append("  </files-modified>")

    git_events = [e for e in events if e.category == "git"]
    if git_events:
        lines.append("  <git-ops>")
        for e in git_events[-10:]:
            op_str = _format_git_event(e)
            if op_str:
                lines.append(f"    <op>{_escape_xml(op_str)}</op>")
        lines.append("  </git-ops>")

    blocker_events = [e for e in events if e.event_type == "blocker"]
    constraint_events = [e for e in events if e.event_type == "constraint"]
    if blocker_events or constraint_events:
        lines.append("  <blockers-and-constraints>")
        for e in blocker_events[-3:]:
            desc = _escape_xml(e.data.get("description", "")[:200])
            lines.append(f"    <blocker>{desc}</blocker>")
        for e in constraint_events[-3:]:
            desc = _escape_xml(e.data.get("description", "")[:200])
            lines.append(f"    <constraint>{desc}</constraint>")
        lines.append("  </blockers-and-constraints>")

    tool_counts = {}
    for e in events:
        if e.event_type == "mcp_tool_use":
            tn = e.data.get("tool_name", "unknown")
            tool_counts[tn] = tool_counts.get(tn, 0) + 1
    if tool_counts:
        lines.append("  <tool-usage>")
        for tn, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
            lines.append(f'    <tool name="{tn}" calls="{count}"/>')
        lines.append("  </tool-usage>")

    if existing_snapshot:
        lines.append("  <previous-snapshot-available>true</previous-snapshot-available>")

    lines.append(f"  <event-total>{sum(counts.values())}</event-total>")
    lines.append("</session-guide>")
    return "\n".join(lines) + "\n"


def _build_prompt_section(events: list[SessionEvent]) -> str:
    prompt_events = [e for e in events if e.event_type == "user_prompt"]
    if not prompt_events:
        return ""
    last = prompt_events[-1]
    text = last.data.get("text", "")[:500]
    return f"  <last-prompt>{_escape_xml(text)}</last-prompt>\n"


def _build_tasks_section(events: list[SessionEvent]) -> str:
    task_events = [e for e in events if e.category == "tasks"]
    if not task_events:
        return ""
    lines = ["  <tasks>"]
    seen: set[str] = set()
    for e in reversed(task_events):
        task_id = e.data.get("id", e.data.get("subject", ""))
        if task_id in seen:
            continue
        seen.add(task_id)
        status = "done" if e.event_type == "task_complete" else e.data.get("status", "pending")
        subject = e.data.get("subject", e.data.get("description", ""))[:100]
        lines.append(f'    <task status="{status}">{_escape_xml(subject)}</task>')
    lines.append("  </tasks>")
    return "\n".join(lines) + "\n"


def _build_errors_section(events: list[SessionEvent]) -> str:
    error_events = [e for e in events if e.event_type == "error"]
    if not error_events:
        return ""
    lines = ["  <errors>"]
    for e in error_events[-5:]:
        tool = e.source_tool
        msg = e.data.get("stderr", e.data.get("command", ""))[:200]
        lines.append(f'    <unresolved tool="{tool}">{_escape_xml(msg)}</unresolved>')
    lines.append("  </errors>")
    return "\n".join(lines) + "\n"


def _build_files_section(events: list[SessionEvent]) -> str:
    file_events = [e for e in events if e.event_type in ("file_edit", "file_write")]
    if not file_events:
        return ""
    lines = ["  <files-modified>"]
    seen: set[str] = set()
    for e in reversed(file_events):
        fp = e.data.get("file_path", "")
        if fp in seen:
            continue
        seen.add(fp)
        if e.event_type == "file_write":
            size = e.data.get("size_bytes", 0)
            lines.append(f"    <file>{_escape_xml(fp)} (created, {size}B)</file>")
        else:
            added = e.data.get("lines_added", 0)
            removed = e.data.get("lines_removed", 0)
            lines.append(f"    <file>{_escape_xml(fp)} (edited, +{added}/-{removed})</file>")
    lines.append("  </files-modified>")
    return "\n".join(lines) + "\n"


def _build_git_section(events: list[SessionEvent]) -> str:
    git_events = [e for e in events if e.category == "git"]
    if not git_events:
        return ""
    lines = ["  <git-ops>"]
    for e in git_events[-10:]:
        op_str = _format_git_event(e)
        if op_str:
            lines.append(f"    <op>{_escape_xml(op_str)}</op>")
    lines.append("  </git-ops>")
    return "\n".join(lines) + "\n"


def _build_context_section(
    p1_events: list[SessionEvent],
    p2_events: list[SessionEvent],
) -> str:
    context_items: list[str] = []

    for e in p1_events:
        if e.event_type == "plan_enter":
            desc = e.data.get("description", "")[:200]
            context_items.append(f"    <plan>{_escape_xml(desc)}</plan>")
        elif e.event_type == "plan_exit":
            state = e.data.get("state", "")[:200]
            context_items.append(f"    <plan-result>{_escape_xml(state)}</plan-result>")

    for e in p2_events:
        if e.event_type == "blocker":
            desc = e.data.get("description", "")[:200]
            context_items.append(f"    <blocker>{_escape_xml(desc)}</blocker>")
        elif e.event_type == "constraint":
            desc = e.data.get("description", "")[:200]
            context_items.append(f"    <constraint>{_escape_xml(desc)}</constraint>")
        elif e.event_type == "error_fix":
            fix = e.data.get("fix", "")[:200]
            context_items.append(f"    <decision>{_escape_xml(fix)}</decision>")

    if not context_items:
        return ""
    return "  <context>\n" + "\n".join(context_items) + "\n  </context>\n"


def _build_tools_section(events: list[SessionEvent]) -> str:
    tool_counts: dict[str, int] = {}
    for e in events:
        if e.event_type == "mcp_tool_use":
            tn = e.data.get("tool_name", "unknown")
            tool_counts[tn] = tool_counts.get(tn, 0) + 1
    if not tool_counts:
        return ""
    lines = ["  <tools>"]
    for tn, count in sorted(tool_counts.items(), key=lambda x: -x[1]):
        lines.append(f'    <tool name="{tn}" calls="{count}"/>')
    lines.append("  </tools>")
    return "\n".join(lines) + "\n"


def _format_git_event(event: SessionEvent) -> str:
    d = event.data
    if event.event_type == "git_commit":
        h = d.get("hash", "")[:7]
        msg = d.get("message", "")[:80]
        return f"commit {h}: {msg}"
    if event.event_type == "git_checkout":
        return f"checkout {d.get('branch', '')}"
    if event.event_type == "git_merge":
        return f"merge {d.get('branch', '')} ({d.get('result', '')})"
    if event.event_type == "git_push":
        return f"push {d.get('remote', '')} {d.get('branch', '')}"
    if event.event_type == "git_pull":
        return f"pull {d.get('remote', '')} {d.get('branch', '')}"
    if event.event_type == "git_diff":
        ins, dels = d.get("insertions", 0), d.get("deletions", 0)
        return f"diff {d.get('file_count', 0)} files (+{ins}/-{dels})"
    if event.event_type == "git_status":
        m, a = d.get("modified", 0), d.get("added", 0)
        dl, u = d.get("deleted", 0), d.get("untracked", 0)
        return f"status M:{m} A:{a} D:{dl} ?:{u}"
    return ""


def _truncate_section(section: str, max_bytes: int) -> str:
    if max_bytes <= 20:
        return ""
    encoded = section.encode("utf-8")
    if len(encoded) <= max_bytes:
        return section
    truncated = encoded[:max_bytes - 15].decode("utf-8", errors="ignore")
    last_newline = truncated.rfind("\n")
    if last_newline > 0:
        truncated = truncated[:last_newline]
    return truncated + "\n  <!-- truncated -->\n"


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _find_last_event(events: list[SessionEvent], event_type: str) -> SessionEvent | None:
    for e in reversed(events):
        if e.event_type == event_type:
            return e
    return None
