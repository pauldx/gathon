"""JS/TS filters — npm, pnpm, tsc, eslint, vitest, playwright, next, prettier, prisma."""

from __future__ import annotations

import json
import re
from collections import Counter

from gathon.cli_token_parse.engine import register

_NPM_NOISE = re.compile(r"^(npm\s+WARN|npm\s+notice|npm\s+timing|added\s+\d+|up to date|\s*$)")
_TSC_ERR_RE = re.compile(r"^(.+?)\((\d+),(\d+)\):\s*error\s+(TS\d+):\s*(.+)")


@register(r"^npm\s+(?:install|ci|i)(?:\s|$)", "npm_install")
def filter_npm_install(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [ln for ln in combined.splitlines() if not _NPM_NOISE.match(ln)]
    if not lines:
        return "ok\n"
    return "\n".join(lines[:10]) + "\n"


@register(r"^npm\s+(?:run\s+)?test", "npm_test")
def filter_npm_test(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [
        ln for ln in combined.splitlines()
        if not _NPM_NOISE.match(ln) and not ln.startswith(">")
    ]
    if not lines:
        return "ok\n"
    return "\n".join(lines[:30]) + "\n"


@register(r"^pnpm\s+(?:install|i|add)(?:\s|$)", "pnpm_install")
def filter_pnpm_install(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [ln for ln in combined.splitlines() if ln.strip() and "Progress" not in ln]
    if not lines:
        return "ok\n"
    return "\n".join(lines[:10]) + "\n"


@register(r"^pnpm\s+(?:list|ls)(?:\s|$)", "pnpm_list")
def filter_pnpm_list(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        deps = data[0].get("dependencies", {}) if data else {}
        parts = [f"pnpm list: {len(deps)} dependencies"]
        for name, info in list(deps.items())[:20]:
            ver = info.get("version", "?")
            parts.append(f"  {name} ({ver})")
        if len(deps) > 20:
            parts.append(f"  ... +{len(deps) - 20} more")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError, IndexError):
        pass
    return stdout


@register(r"^(?:npx\s+)?tsc(?:\s|$)", "tsc")
def filter_tsc(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    errors: list[tuple[str, str, str, str, str]] = []
    by_code: Counter[str] = Counter()
    by_file: Counter[str] = Counter()

    for line in combined.splitlines():
        m = _TSC_ERR_RE.match(line)
        if m:
            fp, line_no, col, code, msg = m.groups()
            errors.append((fp, line_no, col, code, msg))
            by_code[code] += 1
            by_file[fp] += 1

    if not errors:
        if "error" in combined.lower():
            return combined
        return "tsc: ok\n"

    parts = [f"TypeScript: {len(errors)} errors in {len(by_file)} files"]
    if by_code:
        top = ", ".join(f"{c} ({n}x)" for c, n in by_code.most_common(5))
        parts.append(f"Top codes: {top}")
    for fp, cnt in by_file.most_common(10):
        parts.append(f"\n  {fp} ({cnt} errors)")
        file_errs = [e for e in errors if e[0] == fp]
        for _, ln, _, code, msg in file_errs[:3]:
            parts.append(f"    L{ln}: [{code}] {msg[:70]}")
    return "\n".join(parts) + "\n"


@register(r"^(?:npx\s+)?(?:eslint|biome\s+(?:check|lint))", "eslint")
def filter_eslint(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        total_err = sum(d.get("errorCount", 0) for d in data)
        total_warn = sum(d.get("warningCount", 0) for d in data)
        files_with_issues = sum(
            1 for d in data
            if d.get("errorCount", 0) + d.get("warningCount", 0) > 0
        )

        if total_err == 0 and total_warn == 0:
            return "ESLint: clean\n"

        by_rule: Counter[str] = Counter()
        for d in data:
            for msg in d.get("messages", []):
                by_rule[msg.get("ruleId", "?")] += 1

        parts = [f"ESLint: {total_err} errors, {total_warn} warnings in {files_with_issues} files"]
        if by_rule:
            parts.append("Top rules:")
            for rule, cnt in by_rule.most_common(5):
                parts.append(f"  {rule} ({cnt}x)")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout


@register(r"^(?:npx\s+)?vitest\s+run", "vitest")
def filter_vitest(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        passed = data.get("numPassedTests", 0)
        failed = data.get("numFailedTests", 0)
        skipped = data.get("numPendingTests", 0)

        if failed == 0:
            return f"Vitest: {passed} passed, {skipped} skipped\n"

        parts = [f"Vitest: {passed} passed, {failed} failed, {skipped} skipped"]
        for suite in data.get("testResults", []):
            for result in suite.get("assertionResults", []):
                if result.get("status") == "failed":
                    name = result.get("fullName", "?")
                    msgs = result.get("failureMessages", [])
                    parts.append(f"  FAIL: {name[:80]}")
                    if msgs:
                        parts.append(f"    {msgs[0][:100]}")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass

    combined = stdout + stderr
    summary_re = re.compile(r"(\d+)\s+passed|(\d+)\s+failed")
    p = f = 0
    for m in summary_re.finditer(combined):
        if m.group(1):
            p = int(m.group(1))
        if m.group(2):
            f = int(m.group(2))
    if p or f:
        return f"Vitest: {p} passed, {f} failed\n"
    return combined


@register(r"^(?:npx\s+)?(?:jest)(?:\s|$)", "jest")
def filter_jest(stdout: str, stderr: str, args: list[str]) -> str:
    return filter_vitest(stdout, stderr, args)


@register(r"^(?:npx\s+)?playwright\s+test", "playwright")
def filter_playwright(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        suites = data.get("suites", [])
        passed = failed = skipped = 0
        failures: list[str] = []

        def walk(suite: dict) -> None:
            nonlocal passed, failed, skipped
            for spec in suite.get("specs", []):
                for test in spec.get("tests", []):
                    for result in test.get("results", []):
                        st = result.get("status", "")
                        if st == "passed":
                            passed += 1
                        elif st == "failed":
                            failed += 1
                            failures.append(spec.get("title", "?"))
                        elif st == "skipped":
                            skipped += 1
            for child in suite.get("suites", []):
                walk(child)

        for s in suites:
            walk(s)

        if failed == 0:
            return f"Playwright: {passed} passed, {skipped} skipped\n"
        parts = [f"Playwright: {passed} passed, {failed} failed, {skipped} skipped"]
        for f_name in failures[:5]:
            parts.append(f"  FAIL: {f_name}")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass

    combined = stdout + stderr
    summary = re.search(r"(\d+)\s+passed.*?(\d+)\s+failed", combined)
    if summary:
        return f"Playwright: {summary.group(1)} passed, {summary.group(2)} failed\n"
    passed_m = re.search(r"(\d+)\s+passed", combined)
    if passed_m:
        return f"Playwright: {passed_m.group(1)} passed\n"
    return combined


@register(r"^(?:npx\s+)?next\s+build", "next_build")
def filter_next_build(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    static = dynamic = 0
    routes: list[str] = []

    for line in combined.splitlines():
        stripped = line.strip()
        if stripped[:1] in {"○", "●", "ƒ", "λ"}:
            routes.append(stripped[:80])
            if stripped.startswith("○"):
                static += 1
            else:
                dynamic += 1

    if not routes:
        lines = [ln for ln in combined.splitlines() if ln.strip() and "Compiling" not in ln]
        return "\n".join(lines[:20]) + "\n"

    parts = [f"Next.js Build: {len(routes)} routes ({static} static, {dynamic} dynamic)"]
    for r in routes[:15]:
        parts.append(f"  {r}")
    if len(routes) > 15:
        parts.append(f"  ... +{len(routes) - 15} more")
    return "\n".join(parts) + "\n"


@register(r"^(?:npx\s+)?prettier\s+", "prettier")
def filter_prettier(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [ln for ln in combined.splitlines() if ln.strip()]

    if not lines:
        return "Prettier: all files formatted\n"

    if any("All matched files" in ln for ln in lines):
        return "Prettier: all files formatted\n"

    file_lines = [ln for ln in lines if not ln.startswith("[")]
    if file_lines:
        parts = [f"Prettier: {len(file_lines)} files need formatting"]
        for f in file_lines[:10]:
            parts.append(f"  {f.strip()}")
        if len(file_lines) > 10:
            parts.append(f"  ... +{len(file_lines) - 10} more")
        return "\n".join(parts) + "\n"
    return combined


@register(r"^(?:npx\s+)?prisma\s+generate", "prisma_generate")
def filter_prisma_generate(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [
        ln for ln in combined.splitlines()
        if ln.strip() and "████" not in ln and "░░░░" not in ln and "prisma:info" not in ln.lower()
    ]
    if not lines:
        return "prisma generate: ok\n"
    return "\n".join(lines[:10]) + "\n"
