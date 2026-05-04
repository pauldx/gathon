"""Database CLI output compression filters."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register


_MAX_DB_ROWS = 50
_PSQL_SEP_RE = re.compile(r"^[-+|]+$")
_ROW_COUNT_RE = re.compile(r"^(?:\((\d+) rows?(?:\)|$)|(\d+) rows? in set)")


def _compact_table(lines: list[str], max_rows: int = _MAX_DB_ROWS) -> str:
    """Generic table compactor for DB CLI output.

    Keeps header line(s), separator line, data rows up to max_rows,
    and appends row count footer.
    """
    if len(lines) <= max_rows + 3:
        return "\n".join(lines)

    result = []
    header_done = False
    data_rows = 0

    for line in lines:
        if not header_done:
            result.append(line)
            if _PSQL_SEP_RE.match(line):
                header_done = True
        elif data_rows < max_rows:
            result.append(line)
            if line.strip() and not _PSQL_SEP_RE.match(line):
                data_rows += 1
        elif not _ROW_COUNT_RE.search(line):
            pass

    omitted = len(lines) - len(result) - 2
    if omitted > 0:
        result.append(f"({omitted} more rows)")

    return "\n".join(result)


@register(r"^psql(?:\s|$)", "psql")
def filter_psql(stdout: str, stderr: str, args: list[str]) -> str:
    """Compact psql query output: header + 50 rows + count."""
    lines = stdout.splitlines()
    return _compact_table(lines, _MAX_DB_ROWS)


@register(r"^mysql(?:\s|$)", "mysql")
def filter_mysql(stdout: str, stderr: str, args: list[str]) -> str:
    """Compact mysql query output: header + 50 rows + count."""
    lines = stdout.splitlines()
    return _compact_table(lines, _MAX_DB_ROWS)


@register(r"^sqlite3(?:\s|$)", "sqlite3")
def filter_sqlite3(stdout: str, stderr: str, args: list[str]) -> str:
    """Compact sqlite3 query output by mode: table/list/csv."""
    lines = stdout.splitlines()
    if len(lines) <= _MAX_DB_ROWS + 2:
        return stdout

    result = []
    data_rows = 0

    for line in lines:
        if data_rows < _MAX_DB_ROWS:
            result.append(line)
            if line.strip():
                data_rows += 1
        else:
            break

    omitted = len(lines) - data_rows
    if omitted > 0:
        result.append(f"({omitted} more rows)")

    return "\n".join(result)
