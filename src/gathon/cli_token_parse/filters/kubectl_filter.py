"""kubectl output compression filters."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register


@register(r"^kubectl\s+get\s+", "kubectl_get")
def filter_kubectl_get(stdout: str, stderr: str, args: list[str]) -> str:
    """Compact kubectl get output: header + first 30 rows + row count."""
    lines = stdout.splitlines()
    if len(lines) <= 32:
        return stdout

    header = lines[0] if lines else ""
    data = lines[1:31]
    omitted = len(lines) - 32
    footer = f"({omitted} more rows omitted)"

    return "\n".join([header] + data + [footer])


@register(r"^kubectl\s+(?:apply|create|delete)\s+", "kubectl_apply")
def filter_kubectl_apply(stdout: str, stderr: str, args: list[str]) -> str:
    """Summarize kubectl apply/create/delete: count operations by type."""
    lines = (stdout + stderr).splitlines()
    if not lines:
        return stdout + stderr

    created_count = sum(1 for line in lines if "created" in line.lower())
    configured_count = sum(1 for line in lines if "configured" in line.lower())
    deleted_count = sum(1 for line in lines if "deleted" in line.lower())
    unchanged_count = sum(1 for line in lines if "unchanged" in line.lower())

    summary = []
    if created_count:
        summary.append(f"{created_count} created")
    if configured_count:
        summary.append(f"{configured_count} configured")
    if deleted_count:
        summary.append(f"{deleted_count} deleted")
    if unchanged_count:
        summary.append(f"{unchanged_count} unchanged")

    if summary:
        return " | ".join(summary)
    return stdout + stderr


@register(r"^kubectl\s+describe\s+", "kubectl_describe")
def filter_kubectl_describe(stdout: str, stderr: str, args: list[str]) -> str:
    """Extract key sections from kubectl describe: Name, Namespace, Status, Events."""
    lines = stdout.splitlines()
    result = []
    current_section = None
    events_started = False

    for line in lines:
        if line.startswith("Name:"):
            result.append(line)
        elif line.startswith("Namespace:"):
            result.append(line)
        elif line.startswith("Status:"):
            result.append(line)
        elif line.startswith("Events:"):
            events_started = True
            result.append(line)
        elif events_started and (line.startswith("---") or (line and not line[0].isspace())):
            events_started = False
        elif events_started:
            result.append(line)

    return "\n".join(result) if result else stdout
