"""Cargo filter — compact build/test/clippy output."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register

_ERROR_RE = re.compile(r"^error(\[E\d+\])?:\s*(.+)", re.MULTILINE)
_WARN_RE = re.compile(r"^warning:\s*(.+)", re.MULTILINE)
_TEST_SUMMARY_RE = re.compile(r"test result: (\w+)\.\s+(\d+) passed;\s+(\d+) failed")
_COMPILE_NOISE = re.compile(r"^\s*(Compiling|Downloading|Downloaded|Blocking|Updating|Fetching)\s+")
_TIME_RE = re.compile(r"Finished.*?in\s+([\d.]+)s")


@register(r"^cargo\s+build", "cargo_build")
def filter_cargo_build(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    errors = _ERROR_RE.findall(combined)
    warnings = [m for m in _WARN_RE.findall(combined) if "generated" not in m]
    if not errors and not warnings:
        time_m = _TIME_RE.search(combined)
        t = f" ({time_m.group(1)}s)" if time_m else ""
        return f"cargo build: ok{t}\n"

    parts = [f"cargo build: {len(errors)} errors, {len(warnings)} warnings"]
    for _, msg in errors[:10]:
        parts.append(f"  E: {msg[:100]}")
    for msg in warnings[:5]:
        parts.append(f"  W: {msg[:100]}")
    return "\n".join(parts) + "\n"


@register(r"^cargo\s+test", "cargo_test")
def filter_cargo_test(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    total_passed = 0
    total_failed = 0
    suites = 0
    failures: list[str] = []

    for m in _TEST_SUMMARY_RE.finditer(combined):
        suites += 1
        total_passed += int(m.group(2))
        total_failed += int(m.group(3))

    for line in combined.splitlines():
        if line.startswith("test ") and "... FAILED" in line:
            name = line.split("...")[0].replace("test ", "").strip()
            failures.append(name)

    time_m = _TIME_RE.search(combined)
    t = f", {time_m.group(1)}s" if time_m else ""

    if total_failed == 0 and total_passed > 0:
        return f"cargo test: {total_passed} passed ({suites} suites{t})\n"

    parts = [f"cargo test: {total_passed} passed, {total_failed} failed ({suites} suites{t})"]
    for f in failures[:5]:
        parts.append(f"  FAIL: {f}")
    if len(failures) > 5:
        parts.append(f"  ... +{len(failures) - 5} more")
    return "\n".join(parts) + "\n"


@register(r"^cargo\s+clippy", "cargo_clippy")
def filter_cargo_clippy(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    errors = _ERROR_RE.findall(combined)
    warnings = [m for m in _WARN_RE.findall(combined) if "generated" not in m]

    if not errors and not warnings:
        return "cargo clippy: ok\n"

    parts = [f"cargo clippy: {len(errors)} errors, {len(warnings)} warnings"]
    for _, msg in errors[:10]:
        parts.append(f"  E: {msg[:100]}")
    for msg in warnings[:10]:
        parts.append(f"  W: {msg[:100]}")
    return "\n".join(parts) + "\n"


@register(r"^cargo\s+check", "cargo_check")
def filter_cargo_check(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    errors = _ERROR_RE.findall(combined)
    if not errors:
        return "cargo check: ok\n"
    parts = [f"cargo check: {len(errors)} errors"]
    for _, msg in errors[:10]:
        parts.append(f"  E: {msg[:100]}")
    return "\n".join(parts) + "\n"


def _strip_noise(text: str) -> str:
    return "\n".join(
        ln for ln in text.splitlines()
        if not _COMPILE_NOISE.match(ln)
    )
