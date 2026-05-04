"""Core filter dispatcher: match commands to filters, execute, compress output."""

from __future__ import annotations

import re
import shlex
import subprocess
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from gathon.cli_token_parse import FilterResult
from gathon.tokens import estimate_tokens

FilterFn = Callable[[str, str, list[str]], str]


@dataclass
class FilterRule:
    pattern: re.Pattern[str]
    fn: FilterFn
    name: str


_ENV_PREFIX_RE = re.compile(
    r"^(?:[A-Z_][A-Z0-9_]*=[^\s]*\s+)+", re.ASCII,
)

_STREAM_THRESHOLD = 25_000  # tokens; ~100K chars

FILTER_REGISTRY: list[FilterRule] = []


def register(pattern: str, name: str) -> Callable[[FilterFn], FilterFn]:
    """Decorator to register a filter function."""
    compiled = re.compile(pattern, re.IGNORECASE)

    def decorator(fn: FilterFn) -> FilterFn:
        FILTER_REGISTRY.append(FilterRule(compiled, fn, name))
        return fn

    return decorator


def _strip_env_prefix(cmd: str) -> str:
    return _ENV_PREFIX_RE.sub("", cmd).strip()


def _find_filter(cmd: str) -> FilterRule | None:
    clean = _strip_env_prefix(cmd)
    for rule in FILTER_REGISTRY:
        if rule.pattern.search(clean):
            return rule
    return None


def _find_all_filters(cmd: str) -> list[FilterRule]:
    """Return ALL matching FilterRules for a command."""
    clean = _strip_env_prefix(cmd)
    return [rule for rule in FILTER_REGISTRY if rule.pattern.search(clean)]


def _rank_filters(matches: list[FilterRule]) -> list[FilterRule]:
    """Sort matches by historical average savings_pct descending.

    Queries CtpTelemetryDB for performance of each filter.
    On any exception, returns matches unchanged.
    Filters with higher avg_savings_pct are ranked first.
    """
    if not matches:
        return matches

    try:
        from gathon.cli_token_parse.telemetry import CtpTelemetryDB
        db = CtpTelemetryDB()
        scores = {}
        for rule in matches:
            scores[rule.name] = db.get_filter_performance(rule.name)
        db.close()
        return sorted(matches, key=lambda r: scores.get(r.name, 0.0), reverse=True)
    except Exception:
        return matches


def _find_best_filter(
    cmd: str, stdout: str, stderr: str, args: list[str],
) -> tuple[FilterRule, str] | None:
    """Find and run the best matching filter for a command.

    If no filters match: returns None.
    If one filter matches: runs it directly without executor overhead.
    If multiple filters match: runs all in parallel (max 4 workers),
    returns the one producing the shortest output (fewest tokens).

    Args are snapshotted from FILTER_REGISTRY before spawning threads
    to avoid race conditions during concurrent execution.
    """
    matches = _find_all_filters(cmd)
    if not matches:
        return None

    matches = _rank_filters(matches)

    if len(matches) == 1:
        try:
            result = matches[0].fn(stdout, stderr, args)
            return (matches[0], result)
        except Exception:
            return None

    snapshot = list(matches)
    max_workers = min(len(snapshot), 4)

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(rule.fn, stdout, stderr, args): rule
            for rule in snapshot
        }
        for future in as_completed(futures):
            rule = futures[future]
            try:
                output = future.result()
                results.append((rule, output))
            except Exception:
                pass

    if not results:
        return (snapshot[0], stdout + stderr)

    best_rule, best_output = min(results, key=lambda x: len(x[1]))
    return (best_rule, best_output)


def has_filter(cmd: str) -> bool:
    return _find_filter(cmd) is not None


def compose(*fns: FilterFn) -> FilterFn:
    """Compose multiple FilterFns into a pipeline.

    Returns a new FilterFn that pipes stdout through each fn sequentially.
    Output of fn[i] becomes the stdout argument of fn[i+1].
    stderr and args are forwarded unchanged to each fn.
    """
    def composed(stdout: str, stderr: str, args: list[str]) -> str:
        result = stdout
        for fn in fns:
            result = fn(result, stderr, args)
        return result
    return composed


def _truncate_large(text: str, keep_lines: int = 50) -> str:
    """Truncate large output to head + tail with omission marker.

    If line count <= 2*keep_lines, returns text unchanged.
    Otherwise keeps first keep_lines and last keep_lines, inserts
    '[… N lines omitted …]' marker in between.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) <= keep_lines * 2:
        return text

    head = lines[:keep_lines]
    tail = lines[-keep_lines:]
    omitted = len(lines) - keep_lines * 2

    result = "".join(head)
    result += f"[... {omitted} lines omitted ...]\n"
    result += "".join(tail)

    return result


def run_command(cmd: str) -> tuple[str, str, int]:
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=120,
        )
        return proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out after 120s", 1
    except Exception as e:
        return "", str(e), 1


def filter_command(cmd_string: str) -> FilterResult:
    """Main entry: run command through matching filter or passthrough."""
    from gathon.cli_token_parse.cache import _FILTER_CACHE

    cached = _FILTER_CACHE.get(cmd_string)
    if cached is not None:
        return FilterResult(
            output=cached.output,
            exit_code=cached.exit_code,
            filter_name=cached.filter_name,
            before_tokens=cached.before_tokens,
            after_tokens=cached.after_tokens,
            cache_hit=True,
        )

    start = time.monotonic()
    stdout, stderr, exit_code = run_command(cmd_string)
    elapsed_ms = (time.monotonic() - start) * 1000

    raw_output = stdout + stderr if stderr else stdout
    before_tok = estimate_tokens(raw_output)

    try:
        args = shlex.split(cmd_string)
    except ValueError:
        args = cmd_string.split()

    best = _find_best_filter(cmd_string, stdout, stderr, args)

    if best is None:
        result = FilterResult(
            output=raw_output,
            exit_code=exit_code,
            filter_name="passthrough",
            before_tokens=before_tok,
            after_tokens=before_tok,
        )
        _FILTER_CACHE.put(cmd_string, result)
        return result

    rule, filtered = best

    after_tok = estimate_tokens(filtered)

    if after_tok > _STREAM_THRESHOLD:
        filtered = _truncate_large(filtered)
        after_tok = estimate_tokens(filtered)

    try:
        from gathon.cli_token_parse.telemetry import CtpTelemetryDB
        db = CtpTelemetryDB()
        db.log_filter(
            rule.name, cmd_string, before_tok, after_tok, elapsed_ms,
        )
        db.close()
    except Exception:
        pass

    result = FilterResult(
        output=filtered,
        exit_code=exit_code,
        filter_name=rule.name,
        before_tokens=before_tok,
        after_tokens=after_tok,
    )
    _FILTER_CACHE.put(cmd_string, result)
    return result


def load_filters() -> None:
    """Import all filter modules to trigger registration."""
    import gathon.cli_token_parse.filters  # noqa: F401
    from gathon.cli_token_parse.cache import _FILTER_CACHE
    _FILTER_CACHE.invalidate()
