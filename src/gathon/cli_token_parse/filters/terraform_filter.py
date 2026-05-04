"""Terraform output compression filters."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register


_PLAN_SUMMARY_RE = re.compile(r"Plan:\s+(\d+) to add,\s+(\d+) to change,\s+(\d+) to destroy")
_RESOURCE_CHANGE_RE = re.compile(r"^\s*([+~\-])\s+resource")


@register(r"^terraform\s+plan(?:\s|$)", "terraform_plan")
def filter_terraform_plan(stdout: str, stderr: str, args: list[str]) -> str:
    """Extract terraform plan summary and resource changes (limit 20)."""
    lines = stdout.splitlines()
    result = []

    summary_line = None
    for line in lines:
        if "Plan:" in line:
            summary_line = line
            result.append(line)
            break

    change_count = 0
    for line in lines:
        if _RESOURCE_CHANGE_RE.match(line):
            if change_count < 20:
                result.append(line)
                change_count += 1
            elif change_count == 20:
                omitted = sum(1 for l in lines if _RESOURCE_CHANGE_RE.match(l)) - 20
                if omitted > 0:
                    result.append(f"... {omitted} more resource changes omitted")
                change_count += 1

    return "\n".join(result) if result else stdout


@register(r"^terraform\s+apply(?:\s|$)", "terraform_apply")
def filter_terraform_apply(stdout: str, stderr: str, args: list[str]) -> str:
    """Keep terraform apply status lines and resource counts."""
    lines = (stdout + stderr).splitlines()
    result = []

    for line in lines:
        if any(x in line for x in ["Apply complete", "Error", "resource created", "resource destroyed", "resource updated"]):
            result.append(line)

    return "\n".join(result) if result else (stdout + stderr)


@register(r"^terraform\s+state\s+(?:list|show)(?:\s|$)", "terraform_state")
def filter_terraform_state(stdout: str, stderr: str, args: list[str]) -> str:
    """Truncate terraform state output at 50 resources."""
    lines = stdout.splitlines()
    if len(lines) <= 52:
        return stdout

    result = lines[:50]
    omitted = len(lines) - 50
    result.append(f"({omitted} more resources omitted)")

    return "\n".join(result)


@register(r"^terraform\s+show(?:\s|$)", "terraform_show")
def filter_terraform_show(stdout: str, stderr: str, args: list[str]) -> str:
    """Extract resource blocks and skip detailed attribute diffs."""
    lines = stdout.splitlines()
    result = []
    in_resource = False
    indent_depth = 0

    for line in lines:
        if line.strip().startswith("resource "):
            in_resource = True
            result.append(line)
            indent_depth = len(line) - len(line.lstrip())
        elif in_resource:
            current_indent = len(line) - len(line.lstrip())
            if line.strip() and current_indent <= indent_depth:
                in_resource = False
            elif in_resource and ("=" in line or line.strip().startswith("{")):
                result.append(line)

    return "\n".join(result) if result else stdout
