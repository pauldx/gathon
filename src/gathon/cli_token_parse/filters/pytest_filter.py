"""Pytest filter — failures only + summary line."""

from __future__ import annotations

import re
from enum import Enum, auto

from gathon.cli_token_parse.engine import register

_SUMMARY_RE = re.compile(
    r"(\d+)\s+passed|(\d+)\s+failed|(\d+)\s+error|(\d+)\s+skipped|(\d+)\s+warning",
)
_FAIL_HEADER_RE = re.compile(r"^(FAILED|ERROR)\s+(.+?)(?:\s+-\s+(.+))?$")
_SECTION_RE = re.compile(r"^={3,}\s+(.+?)\s+={3,}$")
_ERROR_LINE_RE = re.compile(r"^\s*(>|E\s+|assert |raise |Error|Exception|Traceback)")

_MAX_FAILURES = 5
_MAX_ERROR_LINES = 3


class _State(Enum):
    HEADER = auto()
    PROGRESS = auto()
    FAILURES = auto()
    SUMMARY = auto()


@register(r"^(?:python\s+-m\s+)?pytest(?:\s|$)", "pytest")
def filter_pytest(stdout: str, stderr: str, args: list[str]) -> str:
    text = stdout + stderr
    lines = text.splitlines()

    state = _State.HEADER
    failures: list[dict] = []
    current_fail: dict | None = None
    summary_line = ""

    for line in lines:
        if _has_summary_counts(line):
            summary_line = line.strip()
            continue

        sm = _SECTION_RE.match(line)
        if sm:
            section = sm.group(1).lower()
            if "failure" in section or "error" in section:
                state = _State.FAILURES
                continue
            if "short test summary" in section:
                state = _State.SUMMARY
                continue
            continue

        if state == _State.FAILURES:
            if line.startswith("_") and len(line) > 10 and line == line[0] * len(line):
                if current_fail:
                    failures.append(current_fail)
                current_fail = {"name": "", "errors": []}
                continue

            if current_fail is not None:
                if not current_fail["name"] and line.strip():
                    current_fail["name"] = line.strip()
                elif _ERROR_LINE_RE.match(line) and len(current_fail["errors"]) < _MAX_ERROR_LINES:
                    current_fail["errors"].append(line.rstrip())

        if state == _State.SUMMARY:
            fm = _FAIL_HEADER_RE.match(line.strip())
            if fm and len(failures) < _MAX_FAILURES:
                name = fm.group(2)
                reason = fm.group(3) or ""
                existing = next((f for f in failures if f["name"] == name), None)
                if not existing:
                    failures.append({"name": name, "errors": [f"  {reason}"] if reason else []})

    if current_fail and current_fail["name"]:
        failures.append(current_fail)

    return _format_output(summary_line, failures)


def _has_summary_counts(line: str) -> bool:
    stripped = line.strip().lstrip("=").strip()
    return bool(_SUMMARY_RE.search(stripped)) and (
        "passed" in stripped or "failed" in stripped or "error" in stripped
    )


def _format_output(summary: str, failures: list[dict]) -> str:
    counts = _parse_summary(summary)
    header = "Pytest: " + ", ".join(
        f"{v} {k}" for k, v in counts.items() if v > 0
    )
    if not any(counts.values()):
        header = "Pytest: No tests collected"

    parts = [header]

    if failures:
        parts.append("")
        for i, f in enumerate(failures[:_MAX_FAILURES], 1):
            parts.append(f"{i}. [FAIL] {f['name']}")
            for err in f["errors"]:
                parts.append(f"     {err.strip()}")

        remaining = len(failures) - _MAX_FAILURES
        if remaining > 0:
            parts.append(f"\n... +{remaining} more failures")

    return "\n".join(parts) + "\n"


def _parse_summary(line: str) -> dict[str, int]:
    counts: dict[str, int] = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    for m in _SUMMARY_RE.finditer(line):
        if m.group(1):
            counts["passed"] = int(m.group(1))
        if m.group(2):
            counts["failed"] = int(m.group(2))
        if m.group(3):
            counts["error"] = int(m.group(3))
        if m.group(4):
            counts["skipped"] = int(m.group(4))
    return counts
