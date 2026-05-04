"""Hook system: Claude Code PostToolUse + git hooks generation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HOOKS_JSON = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "gathon session-pre-tool",
                    }
                ],
            },
        ],
        "PostToolUse": [
            {
                "matcher": "Edit|Write|Bash",
                "command": "gathon update --base HEAD",
            },
            {
                "matcher": "Edit|Write|Read|Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": "gathon session-post-tool",
                    }
                ],
            },
        ],
        "PreCompact": [
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "gathon session-pre-compact",
                    }
                ],
            },
        ],
        "SessionStart": [
            {
                "matcher": "",
                "command": "gathon status",
            },
            {
                "matcher": "",
                "hooks": [
                    {
                        "type": "command",
                        "command": "gathon session-start",
                    }
                ],
            },
        ],
    },
}

PRE_COMMIT_HOOK = """\
#!/bin/sh
# gathon pre-commit: show risk summary
if command -v gathon >/dev/null 2>&1; then
    gathon status 2>/dev/null || true
fi
"""

POST_COMMIT_HOOK = """\
#!/bin/sh
# gathon post-commit: incremental rebuild
if command -v gathon >/dev/null 2>&1; then
    gathon update --base HEAD~1 2>/dev/null &
fi
"""

POST_CHECKOUT_HOOK = """\
#!/bin/sh
# gathon post-checkout: rebuild on branch switch
if command -v gathon >/dev/null 2>&1; then
    gathon build 2>/dev/null &
fi
"""


def install_hooks(repo_root: Path) -> dict[str, Any]:
    """Install Claude Code hooks.json and git hooks."""
    messages: list[str] = []

    claude_dir = repo_root / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    hooks_path = claude_dir / "hooks.json"
    hooks_path.write_text(json.dumps(HOOKS_JSON, indent=2) + "\n")
    messages.append(f"Wrote {hooks_path}")

    git_hooks_dir = repo_root / ".git" / "hooks"
    if git_hooks_dir.exists():
        for name, content in [
            ("pre-commit", PRE_COMMIT_HOOK),
            ("post-commit", POST_COMMIT_HOOK),
            ("post-checkout", POST_CHECKOUT_HOOK),
        ]:
            hook_path = git_hooks_dir / name
            if hook_path.exists():
                messages.append(f"Skipped {name} (exists)")
                continue
            hook_path.write_text(content)
            hook_path.chmod(0o755)
            messages.append(f"Installed {name} hook")
    else:
        messages.append("No .git/hooks dir — skipped git hooks")

    return {"messages": messages}


def generate_hooks_json() -> str:
    """Return hooks.json content as string."""
    return json.dumps(HOOKS_JSON, indent=2)
