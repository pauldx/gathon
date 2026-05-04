"""Docker ps filter — compact container listing."""

from __future__ import annotations

import re

from gathon.cli_token_parse.engine import register, run_command

_PORT_RE = re.compile(r"(?:\d+\.\d+\.\d+\.\d+:)?(\d+)->")

_MAX_CONTAINERS = 15


@register(r"^docker\s+ps(?:\s|$)", "docker_ps")
def filter_docker_ps(stdout: str, stderr: str, args: list[str]) -> str:
    fmt = '{{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}'
    cmd = f'docker ps --format "{fmt}"'
    extra = [a for a in args[2:] if a != "ps"]
    if extra:
        cmd += " " + " ".join(extra)

    out, err, code = run_command(cmd)
    if code != 0:
        return stdout or err

    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        return "[docker] 0 containers\n"

    total = len(lines)
    parts = [f"[docker] {total} containers:"]

    for line in lines[:_MAX_CONTAINERS]:
        fields = line.split("\t")
        if len(fields) < 4:
            continue
        cid = fields[0][:12]
        name = fields[1]
        status = fields[2]
        image = _short_image(fields[3])
        ports = _compact_ports(fields[4]) if len(fields) > 4 else ""

        entry = f"  {cid} {name} {image} {status}"
        if ports:
            entry += f" [{ports}]"
        parts.append(entry)

    remaining = total - _MAX_CONTAINERS
    if remaining > 0:
        parts.append(f"  ... +{remaining} more")

    return "\n".join(parts) + "\n"


def _short_image(image: str) -> str:
    if "/" in image:
        return image.rsplit("/", 1)[-1]
    return image


def _compact_ports(ports_str: str) -> str:
    if not ports_str or not ports_str.strip():
        return ""
    port_nums = _PORT_RE.findall(ports_str)
    if not port_nums:
        return ""
    unique = list(dict.fromkeys(port_nums))
    if len(unique) <= 2:
        return ", ".join(unique)
    return f"{unique[0]}, {unique[1]}, ... +{len(unique) - 2}"
