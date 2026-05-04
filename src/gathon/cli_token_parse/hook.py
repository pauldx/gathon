"""PreToolUse hook for Claude Code — rewrite Bash commands through gathon ctp."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


def hook_main() -> None:
    """Entry point: read stdin JSON, output rewrite JSON or exit silent."""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return

        data = json.loads(raw)
        tool_name = data.get("tool_name", "")
        if tool_name != "Bash":
            return

        tool_input = data.get("tool_input", {})
        command = tool_input.get("command", "")
        if not command or not command.strip():
            return

        if command.strip().startswith("gathon ctp "):
            return

        from gathon.cli_token_parse.engine import has_filter, load_filters
        load_filters()

        if not has_filter(command):
            return

        gathon_bin = shutil.which("gathon")
        if not gathon_bin:
            return

        rewritten = f"gathon ctp {command}"
        result = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "gathon ctp auto-rewrite",
                "updatedInput": {"command": rewritten},
            }
        }
        print(json.dumps(result))

    except Exception:
        pass


def install_hook() -> bool:
    """Add gathon ctp PreToolUse hook to ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        print("~/.claude/settings.json not found")
        return False

    settings = json.loads(settings_path.read_text())

    hooks = settings.setdefault("hooks", {})
    pre_hooks = hooks.setdefault("PreToolUse", [])

    for group in pre_hooks:
        for h in group.get("hooks", []):
            if "gathon" in h.get("command", "") and "ctp-hook" in h.get("command", ""):
                print("gathon ctp hook already installed")
                return True

    hook_entry = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": "gathon ctp-hook",
            }
        ],
    }
    pre_hooks.append(hook_entry)
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print("gathon ctp hook installed in ~/.claude/settings.json")
    print("Restart Claude Code for changes to take effect.")
    return True


def uninstall_hook() -> bool:
    """Remove gathon ctp PreToolUse hook from ~/.claude/settings.json."""
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        return False

    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {})
    pre_hooks = hooks.get("PreToolUse", [])

    new_hooks = [
        g for g in pre_hooks
        if not any(
            "gathon" in h.get("command", "") and "ctp-hook" in h.get("command", "")
            for h in g.get("hooks", [])
        )
    ]

    if len(new_hooks) == len(pre_hooks):
        print("No gathon ctp hook found")
        return False

    if new_hooks:
        hooks["PreToolUse"] = new_hooks
    else:
        del hooks["PreToolUse"]

    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    print("gathon ctp hook removed")
    return True


if __name__ == "__main__":
    hook_main()
