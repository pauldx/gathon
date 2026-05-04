"""Dotnet filters — dotnet build, dotnet test."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register

_BUILD_ERR_RE = re.compile(r":\s*error\s+(\w+):\s*(.+)")
_BUILD_WARN_RE = re.compile(r":\s*warning\s+(\w+):\s*(.+)")
_TEST_PASSED_RE = re.compile(r"Passed!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+)")
_TEST_FAILED_RE = re.compile(r"Failed!\s*-\s*Failed:\s*(\d+),\s*Passed:\s*(\d+)")
_NOISE_RE = re.compile(r"^\s*(Determining|Restoring|Build started|Microsoft)")


@register(r"^dotnet\s+build", "dotnet_build")
def filter_dotnet_build(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    errors = _BUILD_ERR_RE.findall(combined)
    warnings = _BUILD_WARN_RE.findall(combined)

    if not errors and not warnings:
        return "dotnet build: ok\n"

    parts = [f"dotnet build: {len(errors)} errors, {len(warnings)} warnings"]
    for code, msg in errors[:10]:
        parts.append(f"  E [{code}]: {msg[:80]}")
    for code, msg in warnings[:5]:
        parts.append(f"  W [{code}]: {msg[:80]}")
    return "\n".join(parts) + "\n"


@register(r"^dotnet\s+test", "dotnet_test")
def filter_dotnet_test(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr

    m = _TEST_PASSED_RE.search(combined)
    if m:
        failed, passed = int(m.group(1)), int(m.group(2))
        return f"dotnet test: {passed} passed, {failed} failed\n"

    m = _TEST_FAILED_RE.search(combined)
    if m:
        failed, passed = int(m.group(1)), int(m.group(2))
        failures: list[str] = []
        for line in combined.splitlines():
            if "Failed " in line and "::" in line:
                failures.append(line.strip()[:80])
        parts = [f"dotnet test: {passed} passed, {failed} failed"]
        for f in failures[:5]:
            parts.append(f"  {f}")
        return "\n".join(parts) + "\n"

    lines = [ln for ln in combined.splitlines() if ln.strip() and not _NOISE_RE.match(ln)]
    return "\n".join(lines[:20]) + "\n"
