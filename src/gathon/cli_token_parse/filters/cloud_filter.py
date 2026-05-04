"""Cloud filters — aws CLI, curl, wget, docker images/logs, kubectl."""

from __future__ import annotations

import json
import re

from gathon.cli_token_parse.engine import register, run_command

_PROGRESS_RE = re.compile(r"^\s*[\d.]+%|^#+\s|^\s*\r")
_CURL_HEADER_RE = re.compile(r"^[<>*]\s")


@register(r"^aws\s+sts\s+get-caller-identity", "aws_identity")
def filter_aws_identity(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        acct = data.get("Account", "?")
        arn = data.get("Arn", "?")
        return f"AWS: {arn} (account: {acct})\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout


@register(r"^aws\s+ec2\s+describe-instances", "aws_ec2")
def filter_aws_ec2(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        instances = []
        for res in data.get("Reservations", []):
            for inst in res.get("Instances", []):
                iid = inst.get("InstanceId", "?")
                state = inst.get("State", {}).get("Name", "?")
                itype = inst.get("InstanceType", "?")
                name = ""
                for tag in inst.get("Tags", []):
                    if tag.get("Key") == "Name":
                        name = tag.get("Value", "")
                instances.append(f"  {iid} {itype} {state} {name}")

        parts = [f"EC2: {len(instances)} instances"]
        parts.extend(instances[:15])
        if len(instances) > 15:
            parts.append(f"  ... +{len(instances) - 15} more")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout


@register(r"^aws\s+lambda\s+list-functions", "aws_lambda")
def filter_aws_lambda(stdout: str, stderr: str, args: list[str]) -> str:
    try:
        data = json.loads(stdout)
        fns = data.get("Functions", [])
        parts = [f"Lambda: {len(fns)} functions"]
        for fn in fns[:20]:
            name = fn.get("FunctionName", "?")
            runtime = fn.get("Runtime", "?")
            mem = fn.get("MemorySize", "?")
            parts.append(f"  {name} ({runtime}, {mem}MB)")
        if len(fns) > 20:
            parts.append(f"  ... +{len(fns) - 20} more")
        return "\n".join(parts) + "\n"
    except (json.JSONDecodeError, TypeError):
        pass
    return stdout


@register(r"^aws\s+s3\s+ls", "aws_s3")
def filter_aws_s3(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if len(lines) <= 30:
        return stdout
    parts = lines[:20]
    parts.append(f"\n... ({len(lines) - 20} more items)")
    return "\n".join(parts) + "\n"


@register(r"^curl\s+", "curl")
def filter_curl(stdout: str, stderr: str, args: list[str]) -> str:
    output = stdout
    if stderr:
        output += "\n".join(
            ln for ln in stderr.splitlines()
            if not _CURL_HEADER_RE.match(ln) and not _PROGRESS_RE.match(ln)
        )

    try:
        data = json.loads(output.strip())
        compact = json.dumps(data, indent=2)
        lines = compact.splitlines()
        if len(lines) > 50:
            return "\n".join(lines[:40]) + f"\n... ({len(lines) - 40} lines truncated)\n"
        return compact + "\n"
    except (json.JSONDecodeError, TypeError):
        pass

    lines = output.splitlines()
    if len(lines) > 100:
        return "\n".join(lines[:80]) + f"\n... ({len(lines) - 80} lines truncated)\n"
    return output


@register(r"^wget\s+", "wget")
def filter_wget(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + stderr
    lines = [
        ln for ln in combined.splitlines()
        if not _PROGRESS_RE.match(ln) and ln.strip()
    ]
    return "\n".join(lines) + "\n" if lines else "ok\n"


@register(r"^docker\s+images", "docker_images")
def filter_docker_images(stdout: str, stderr: str, args: list[str]) -> str:
    fmt = '{{.Repository}}:{{.Tag}}\t{{.Size}}'
    out, err, code = run_command(f'docker images --format "{fmt}"')
    if code != 0:
        return stdout or err

    lines = [ln for ln in out.strip().splitlines() if ln.strip()]
    if not lines:
        return "[docker] 0 images\n"

    parts = [f"[docker] {len(lines)} images"]
    for line in lines[:15]:
        parts.append(f"  {line}")
    if len(lines) > 15:
        parts.append(f"  ... +{len(lines) - 15} more")
    return "\n".join(parts) + "\n"


@register(r"^docker\s+logs?\s+", "docker_logs")
def filter_docker_logs(stdout: str, stderr: str, args: list[str]) -> str:
    combined = stdout + (stderr if stderr else "")
    lines = combined.splitlines()

    if len(lines) <= 50:
        return combined

    seen: dict[str, int] = {}
    deduped: list[str] = []
    for line in lines[-100:]:
        stripped = line.strip()
        if stripped in seen:
            seen[stripped] += 1
        else:
            seen[stripped] = 1
            deduped.append(line)

    dupes = sum(1 for v in seen.values() if v > 1)
    parts = deduped[-50:]
    if dupes:
        parts.append(f"\n({dupes} duplicate log patterns collapsed)")
    return "\n".join(parts) + "\n"


@register(r"^kubectl\s+(?:get\s+)?pods?", "kubectl_pods")
def filter_kubectl_pods(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if len(lines) <= 1:
        return "No pods found.\n"
    header = lines[0]
    pods = lines[1:]
    parts = [f"[k8s] {len(pods)} pods", header]
    for p in pods[:20]:
        parts.append(p)
    if len(pods) > 20:
        parts.append(f"  ... +{len(pods) - 20} more")
    return "\n".join(parts) + "\n"


@register(r"^kubectl\s+(?:get\s+)?services?", "kubectl_services")
def filter_kubectl_services(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if len(lines) <= 1:
        return "No services found.\n"
    return "\n".join(lines[:20]) + "\n"


@register(r"^kubectl\s+logs?\s+", "kubectl_logs")
def filter_kubectl_logs(stdout: str, stderr: str, args: list[str]) -> str:
    return filter_docker_logs(stdout, stderr, args)


@register(r"^docker\s+compose\s+ps", "docker_compose_ps")
def filter_docker_compose_ps(stdout: str, stderr: str, args: list[str]) -> str:
    lines = stdout.strip().splitlines()
    if not lines:
        return "[compose] 0 services\n"
    parts = [f"[compose] {max(0, len(lines) - 1)} services"]
    parts.extend(lines[:15])
    return "\n".join(parts) + "\n"
