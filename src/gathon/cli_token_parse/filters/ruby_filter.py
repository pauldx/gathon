"""Ruby filters — rake test, rspec, rubocop."""

from __future__ import annotations

import json
import re

from gathon.cli_token_parse.engine import register

_RSPEC_SUMMARY_RE = re.compile(r"(\d+)\s+examples?,\s+(\d+)\s+failures?")
_RAKE_SUMMARY_RE = re.compile(r"(\d+)\s+(?:tests?|runs?),.*?(\d+)\s+failures?")


@register(r"^(?:bundle\s+exec\s+)?rake\s+test", "rake_test")
def filter_rake_test(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    m = _RAKE_SUMMARY_RE.search(combined)
    if not m:
        lines = [ln for ln in combined.splitlines() if ln.strip()]
        return "\n".join(lines[:20]) + "\n"

    total, failed = int(m.group(1)), int(m.group(2))
    passed = total - failed
    if failed == 0:
        return f"Rake test: {passed} passed\n"

    failures: list[str] = []
    for line in combined.splitlines():
        if "Failure:" in line or "Error:" in line:
            failures.append(line.strip()[:80])

    parts = [f"Rake test: {passed} passed, {failed} failed"]
    for f in failures[:5]:
        parts.append(f"  {f}")
    return "\n".join(parts) + "\n"


@register(r"^(?:bundle\s+exec\s+)?rspec", "rspec")
def filter_rspec(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        examples = data.get("summary", {})
        total = examples.get("example_count", 0)
        failed = examples.get("failure_count", 0)
        pending = examples.get("pending_count", 0)
        passed = total - failed - pending

        if failed == 0:
            return f"RSpec: {passed} passed, {pending} pending\n"

        parts = [f"RSpec: {passed} passed, {failed} failed, {pending} pending"]
        for ex in data.get("examples", []):
            if ex.get("status") == "failed":
                desc = ex.get("full_description", "?")[:80]
                msg = ex.get("exception", {}).get("message", "")[:80]
                parts.append(f"  FAIL: {desc}")
                if msg:
                    parts.append(f"    {msg}")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass

    combined = stdout + stderr
    m = _RSPEC_SUMMARY_RE.search(combined)
    if m:
        total, failed = int(m.group(1)), int(m.group(2))
        if failed == 0:
            return f"RSpec: {total} passed\n"
        return f"RSpec: {total - failed} passed, {failed} failed\n"
    return combined


@register(r"^(?:bundle\s+exec\s+)?rubocop", "rubocop")
def filter_rubocop(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        files = data.get("files", [])
        total_offenses = sum(len(f.get("offenses", [])) for f in files)
        files_with = sum(1 for f in files if f.get("offenses"))

        if total_offenses == 0:
            return "RuboCop: clean\n"

        from collections import Counter
        by_cop: Counter[str] = Counter()
        for f in files:
            for o in f.get("offenses", []):
                by_cop[o.get("cop_name", "?")] += 1

        parts = [f"RuboCop: {total_offenses} offenses in {files_with} files"]
        for cop, cnt in by_cop.most_common(5):
            parts.append(f"  {cop} ({cnt}x)")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout
