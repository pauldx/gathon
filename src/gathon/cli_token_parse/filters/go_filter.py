"""Go filters — go test, go build, golangci-lint."""

from __future__ import annotations

import json
import re

from gathon.cli_token_parse.engine import register

_BUILD_ERR_RE = re.compile(r"^(.+?):(\d+):(\d+):\s*(.+)")


@register(r"^go\s+test", "go_test")
def filter_go_test(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    passed = 0
    failed = 0
    packages = set()
    failures: list[str] = []

    try:
        for line in combined.splitlines():
            if not line.strip():
                continue
            ev = json.loads(line)
            action = ev.get("Action", "")
            pkg = ev.get("Package", "")
            test = ev.get("Test", "")
            if pkg:
                packages.add(pkg)
            if action == "pass" and test:
                passed += 1
            elif action == "fail" and test:
                failed += 1
                failures.append(f"{pkg}::{test}")
    except (json.JSONDecodeError, TypeError):
        for line in combined.splitlines():
            if line.startswith("ok"):
                passed += 1
            elif line.startswith("FAIL"):
                failed += 1
                failures.append(line.strip())

    if failed == 0 and passed > 0:
        return f"Go test: {passed} passed ({len(packages)} packages)\n"

    parts = [f"Go test: {passed} passed, {failed} failed ({len(packages)} packages)"]
    for f in failures[:5]:
        parts.append(f"  FAIL: {f}")
    if len(failures) > 5:
        parts.append(f"  ... +{len(failures) - 5} more")
    return "\n".join(parts) + "\n"


@register(r"^go\s+build", "go_build")
def filter_go_build(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    if not combined.strip():
        return "go build: ok\n"

    errors = _BUILD_ERR_RE.findall(combined)
    if not errors:
        return "go build: ok\n"

    parts = [f"go build: {len(errors)} errors"]
    for fp, line, col, msg in errors[:10]:
        parts.append(f"  {fp}:{line}: {msg[:80]}")
    return "\n".join(parts) + "\n"


@register(r"^go\s+vet", "go_vet")
def filter_go_vet(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    if not combined.strip():
        return "go vet: ok\n"
    errors = _BUILD_ERR_RE.findall(combined)
    if not errors:
        return combined
    parts = [f"go vet: {len(errors)} issues"]
    for fp, line, col, msg in errors[:10]:
        parts.append(f"  {fp}:{line}: {msg[:80]}")
    return "\n".join(parts) + "\n"


@register(r"^golangci-lint\s+run", "golangci_lint")
def filter_golangci_lint(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        issues = data.get("Issues") or data.get("issues") or []
        if not issues:
            return "golangci-lint: clean\n"

        from collections import Counter
        by_linter: Counter[str] = Counter()
        by_file: Counter[str] = Counter()
        for iss in issues:
            by_linter[iss.get("FromLinter", "?")] += 1
            pos = iss.get("Pos", {})
            by_file[pos.get("Filename", "?")] += 1

        parts = [f"golangci-lint: {len(issues)} issues in {len(by_file)} files"]
        parts.append("Top linters:")
        for linter, cnt in by_linter.most_common(5):
            parts.append(f"  {linter} ({cnt}x)")
        parts.append("Top files:")
        for fp, cnt in by_file.most_common(10):
            parts.append(f"  {fp} ({cnt})")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout
