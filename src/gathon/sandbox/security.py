"""Minimal security layer — deny dangerous commands before execution."""

from __future__ import annotations

import re

DENY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\s+/\s*$", re.IGNORECASE),
    re.compile(r"\brm\s+(-\w*r\w*f\w*|-\w*f\w*r\w*)\s+/(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bsudo\b"),
    re.compile(r"\bshutdown\b"),
    re.compile(r"\breboot\b"),
    re.compile(r"\bmkfs\b"),
    re.compile(r"\bdd\s+if=/dev/", re.IGNORECASE),
    re.compile(r"\b:(){ :\|:& };:", re.IGNORECASE),  # fork bomb
    re.compile(r"\bchmod\s+(-\w+\s+)*777\s+/\s*$"),
    re.compile(r"\bchmod\s+(-\w+\s+)*777\s+/(?:\s|$)"),
]

# Shell-escape patterns for non-shell languages
_SHELL_ESCAPE_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "python": [
        re.compile(r"\bos\.system\s*\("),
        re.compile(r"\bsubprocess\.\w+\s*\("),
        re.compile(r"\bexec\s*\("),
        re.compile(r"\beval\s*\("),
    ],
    "javascript": [
        re.compile(r"\bchild_process\b"),
        re.compile(r"\bexecSync\s*\("),
        re.compile(r"\bexec\s*\("),
        re.compile(r"\bspawnSync\s*\("),
    ],
    "typescript": [
        re.compile(r"\bchild_process\b"),
        re.compile(r"\bexecSync\s*\("),
        re.compile(r"\bexec\s*\("),
        re.compile(r"\bspawnSync\s*\("),
    ],
    "ruby": [
        re.compile(r"\bsystem\s*\("),
        re.compile(r"`[^`]+`"),
        re.compile(r"\bexec\s*\("),
    ],
    "go": [
        re.compile(r"\bexec\.Command\s*\("),
    ],
    "rust": [
        re.compile(r"\bCommand::new\s*\("),
        re.compile(r"\bstd::process::Command\b"),
    ],
    "php": [
        re.compile(r"\bexec\s*\("),
        re.compile(r"\bsystem\s*\("),
        re.compile(r"\bshell_exec\s*\("),
        re.compile(r"\bpassthru\s*\("),
    ],
    "perl": [
        re.compile(r"\bsystem\s*\("),
        re.compile(r"`[^`]+`"),
    ],
}


def _split_chained(cmd: str) -> list[str]:
    """Split a shell command string on &&, ||, ;, and | operators."""
    segments = re.split(r"\s*(?:&&|\|\||[;|])\s*", cmd)
    return [s.strip() for s in segments if s.strip()]


def check_command(cmd: str, language: str = "shell") -> tuple[bool, str]:
    """Check whether a command is allowed.

    Returns (allowed, reason). If allowed is False, reason explains why.
    """
    if language in ("shell", "bash", "sh"):
        segments = _split_chained(cmd)
        for segment in segments:
            for pattern in DENY_PATTERNS:
                if pattern.search(segment):
                    return False, f"Blocked: dangerous pattern '{pattern.pattern}' in '{segment}'"
        return True, ""

    # Non-shell languages: check for shell escapes
    escape_patterns = _SHELL_ESCAPE_PATTERNS.get(language, [])
    for pattern in escape_patterns:
        if pattern.search(cmd):
            return False, f"Blocked: shell escape '{pattern.pattern}' in {language} code"

    return True, ""
