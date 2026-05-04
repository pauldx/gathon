"""SandboxExecutor — subprocess-isolated code execution with output filtering.

Raw output NEVER enters the LLM context window. Only summaries, search
results, or explicit print() output are returned.
"""

from __future__ import annotations

import logging
import os
import platform
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gathon.sandbox.content_store import ContentStore
from gathon.sandbox.security import check_command
from gathon.tokens import estimate_tokens

logger = logging.getLogger(__name__)

# Hard cap on combined stdout+stderr
_OUTPUT_CAP = 100 * 1024 * 1024  # 100MB

# Threshold for auto-indexing when intent is provided
_INTENT_INDEX_THRESHOLD = 5000  # bytes

# Env vars safe to inherit into sandbox
_PASSTHROUGH_ENV_PREFIXES = (
    "GITHUB_TOKEN", "GH_TOKEN",
    "AWS_", "KUBECONFIG", "SSH_AUTH_SOCK",
    "DOCKER_HOST", "NPM_TOKEN",
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    "HOME", "USER", "PATH", "LANG", "TERM",
    "TMPDIR", "XDG_",
)

_IS_UNIX = platform.system() != "Windows"


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    exit_code: int
    language: str
    elapsed_ms: int
    raw_bytes: int
    context_bytes: int
    indexed: bool = False
    timed_out: bool = False
    capped: bool = False
    token_estimate: int = 0


# Language runtime definitions: (primary, [fallbacks])
_RUNTIMES: dict[str, tuple[str, list[str]]] = {
    "python": ("python3", ["python"]),
    "javascript": ("bun", ["node"]),
    "typescript": ("bun", ["tsx", "ts-node"]),
    "shell": ("bash", ["sh"]),
    "bash": ("bash", ["sh"]),
    "sh": ("sh", []),
    "ruby": ("ruby", []),
    "go": ("go", []),
    "rust": ("rustc", []),
    "php": ("php", []),
    "perl": ("perl", []),
    "r": ("Rscript", []),
    "elixir": ("elixir", []),
}

_EXTENSIONS: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "shell": ".sh",
    "bash": ".sh",
    "sh": ".sh",
    "ruby": ".rb",
    "go": ".go",
    "rust": ".rs",
    "php": ".php",
    "perl": ".pl",
    "r": ".R",
    "elixir": ".exs",
}


def _find_runtime(language: str) -> str | None:
    """Resolve runtime binary with fallback chain."""
    entry = _RUNTIMES.get(language)
    if not entry:
        return None

    primary, fallbacks = entry
    if shutil.which(primary):
        return primary
    for fb in fallbacks:
        if shutil.which(fb):
            return fb
    return None


def _build_env() -> dict[str, str]:
    """Build sanitized environment for subprocess."""
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if any(key.startswith(prefix) or key == prefix for prefix in _PASSTHROUGH_ENV_PREFIXES):
            env[key] = value
    return env


def _wrap_code(language: str, code: str) -> str:
    """Apply language-specific wrappers."""
    if language == "go" and "func main()" not in code:
        if "package main" not in code:
            code = f"package main\n\nimport \"fmt\"\n\nfunc main() {{\n{code}\n_ = fmt.Sprintf\n}}"

    elif language == "php" and not code.strip().startswith("<?"):
        code = f"<?php\n{code}"

    return code


def _prepare_rust(code: str, tmp_dir: Path) -> list[str]:
    """Compile Rust source and return run command."""
    src = tmp_dir / "sandbox.rs"
    binary = tmp_dir / "sandbox"
    src.write_text(code, encoding="utf-8")

    compile_result = subprocess.run(
        ["rustc", str(src), "-o", str(binary)],
        capture_output=True, text=True, timeout=30,
        cwd=str(tmp_dir),
    )
    if compile_result.returncode != 0:
        raise RuntimeError(f"Rust compilation failed:\n{compile_result.stderr}")

    return [str(binary)]


class SandboxExecutor:
    """Execute code in isolated subprocesses with output filtering."""

    def __init__(self, content_store: ContentStore | None = None) -> None:
        self._store = content_store or ContentStore()

    @property
    def store(self) -> ContentStore:
        return self._store

    def execute(
        self,
        language: str,
        code: str,
        timeout: int = 30,
        intent: str | None = None,
    ) -> SandboxResult:
        """Execute code in a subprocess sandbox.

        If intent is provided and output exceeds threshold, auto-indexes
        into ContentStore and returns only relevant snippets.
        """
        language = language.lower().strip()

        # Security check
        allowed, reason = check_command(code, language)
        if not allowed:
            return SandboxResult(
                stdout="", stderr=reason, exit_code=1,
                language=language, elapsed_ms=0,
                raw_bytes=len(reason), context_bytes=len(reason),
            )

        runtime = _find_runtime(language)
        if not runtime:
            checked = _RUNTIMES.get(language, ("?", []))
            msg = f"No runtime for '{language}'. Checked: {checked}"
            return SandboxResult(
                stdout="", stderr=msg, exit_code=127,
                language=language, elapsed_ms=0,
                raw_bytes=len(msg), context_bytes=len(msg),
            )

        code = _wrap_code(language, code)

        with tempfile.TemporaryDirectory(prefix="gathon_sandbox_") as tmp_dir:
            tmp_path = Path(tmp_dir)
            try:
                cmd = self._build_command(language, runtime, code, tmp_path)
            except RuntimeError as exc:
                msg = str(exc)
                return SandboxResult(
                    stdout="", stderr=msg, exit_code=1,
                    language=language, elapsed_ms=0,
                    raw_bytes=len(msg), context_bytes=len(msg),
                )

            result = self._run_process(cmd, tmp_path, timeout, language)

        return self._apply_intent_filter(result, intent)

    def execute_file(
        self, file_path: str, timeout: int = 30, intent: str | None = None,
    ) -> SandboxResult:
        """Read a file and execute it in the sandbox — file content never enters context."""
        path = Path(file_path)
        if not path.exists():
            msg = f"File not found: {file_path}"
            return SandboxResult(
                stdout="", stderr=msg, exit_code=1,
                language="unknown", elapsed_ms=0,
                raw_bytes=len(msg), context_bytes=len(msg),
            )

        # Detect language from extension
        ext = path.suffix.lower()
        lang_map = {v: k for k, v in _EXTENSIONS.items()}
        language = lang_map.get(ext, "shell")

        code = path.read_text(encoding="utf-8")
        return self.execute(language, code, timeout=timeout, intent=intent)

    def batch_execute(self, commands: list[dict[str, Any]]) -> list[SandboxResult]:
        """Run multiple commands sequentially, returning results for each."""
        results: list[SandboxResult] = []
        for cmd in commands:
            language = cmd.get("language", "shell")
            code = cmd.get("code", "")
            timeout = cmd.get("timeout", 30)
            intent = cmd.get("intent")
            results.append(self.execute(language, code, timeout=timeout, intent=intent))
        return results

    def _build_command(
        self, language: str, runtime: str, code: str, tmp_dir: Path,
    ) -> list[str]:
        """Build the command list for subprocess execution."""
        if language == "rust":
            return _prepare_rust(code, tmp_dir)

        if language == "go":
            src = tmp_dir / "main.go"
            src.write_text(code, encoding="utf-8")
            return ["go", "run", str(src)]

        if language in ("shell", "bash", "sh"):
            return [runtime, "-c", code]

        # Write to temp file for interpreted languages
        ext = _EXTENSIONS.get(language, ".txt")
        src = tmp_dir / f"sandbox{ext}"
        src.write_text(code, encoding="utf-8")

        if language == "typescript" and runtime == "bun":
            return ["bun", "run", str(src)]
        if language == "typescript":
            return [runtime, str(src)]

        if language == "javascript" and runtime == "bun":
            return ["bun", "run", str(src)]

        return [runtime, str(src)]

    def _run_process(
        self, cmd: list[str], cwd: Path, timeout: int, language: str,
    ) -> SandboxResult:
        """Execute subprocess with process group isolation and output capping."""
        t0 = time.monotonic()
        stdout_buf: list[bytes] = []
        stderr_buf: list[bytes] = []
        total_bytes = 0
        timed_out = False
        capped = False

        kwargs: dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": str(cwd),
            "env": _build_env(),
        }
        if _IS_UNIX:
            kwargs["preexec_fn"] = os.setsid

        try:
            proc = subprocess.Popen(cmd, **kwargs)
        except FileNotFoundError:
            msg = f"Runtime binary not found: {cmd[0]}"
            return SandboxResult(
                stdout="", stderr=msg, exit_code=127,
                language=language, elapsed_ms=0,
                raw_bytes=len(msg), context_bytes=len(msg),
            )
        except OSError as exc:
            msg = f"Failed to start process: {exc}"
            return SandboxResult(
                stdout="", stderr=msg, exit_code=1,
                language=language, elapsed_ms=0,
                raw_bytes=len(msg), context_bytes=len(msg),
            )

        try:
            # Read incrementally to enforce output cap
            deadline = time.monotonic() + timeout

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break

                # Non-blocking read via communicate with short timeout
                try:
                    out, err = proc.communicate(timeout=min(remaining, 1.0))
                    if out:
                        stdout_buf.append(out)
                        total_bytes += len(out)
                    if err:
                        stderr_buf.append(err)
                        total_bytes += len(err)

                    if total_bytes > _OUTPUT_CAP:
                        capped = True
                    break  # Process finished
                except subprocess.TimeoutExpired:
                    # Read whatever is available and check caps
                    if total_bytes > _OUTPUT_CAP:
                        capped = True
                        break
                    continue

        finally:
            if proc.poll() is None:
                self._kill_process_tree(proc)

        elapsed_ms = int((time.monotonic() - t0) * 1000)

        stdout_raw = b"".join(stdout_buf)
        stderr_raw = b"".join(stderr_buf)

        # Truncate at cap boundary if needed
        if capped:
            max_per_stream = _OUTPUT_CAP // 2
            stdout_raw = stdout_raw[:max_per_stream]
            stderr_raw = stderr_raw[:max_per_stream]

        stdout_str = stdout_raw.decode("utf-8", errors="replace")
        stderr_str = stderr_raw.decode("utf-8", errors="replace")
        raw_bytes = len(stdout_raw) + len(stderr_raw)

        return SandboxResult(
            stdout=stdout_str,
            stderr=stderr_str,
            exit_code=proc.returncode if proc.returncode is not None else -1,
            language=language,
            elapsed_ms=elapsed_ms,
            raw_bytes=raw_bytes,
            context_bytes=raw_bytes,  # Will be reduced by intent filter
            timed_out=timed_out,
            capped=capped,
            token_estimate=estimate_tokens(stdout_str + stderr_str),
        )

    def _apply_intent_filter(self, result: SandboxResult, intent: str | None) -> SandboxResult:
        """If intent provided and output large, auto-index and search."""
        if not intent or result.raw_bytes <= _INTENT_INDEX_THRESHOLD:
            return result

        combined = result.stdout
        if result.stderr:
            combined += f"\n--- STDERR ---\n{result.stderr}"

        self._store.index(
            label=f"sandbox:{result.language}:{intent[:50]}",
            content=combined,
            source_type="sandbox_output",
        )

        search_results = self._store.search(intent, limit=5)

        if not search_results:
            # Fallback: return truncated output
            truncated = combined[:_INTENT_INDEX_THRESHOLD]
            return SandboxResult(
                stdout=truncated,
                stderr=result.stderr[:500] if result.stderr else "",
                exit_code=result.exit_code,
                language=result.language,
                elapsed_ms=result.elapsed_ms,
                raw_bytes=result.raw_bytes,
                context_bytes=len(truncated),
                indexed=True,
                timed_out=result.timed_out,
                capped=result.capped,
                token_estimate=estimate_tokens(truncated),
            )

        # Build filtered output from search results
        lines: list[str] = []
        n = len(search_results)
        lines.append(f"[Indexed {result.raw_bytes}B, {n} matches]")
        lines.append("")

        for sr in search_results:
            lines.append(f"--- {sr.title} (score: {sr.score:.2f}) ---")
            lines.append(sr.snippet)
            lines.append("")

        filtered = "\n".join(lines)

        return SandboxResult(
            stdout=filtered,
            stderr=result.stderr[:500] if result.exit_code != 0 else "",
            exit_code=result.exit_code,
            language=result.language,
            elapsed_ms=result.elapsed_ms,
            raw_bytes=result.raw_bytes,
            context_bytes=len(filtered),
            indexed=True,
            timed_out=result.timed_out,
            capped=result.capped,
            token_estimate=estimate_tokens(filtered),
        )

    @staticmethod
    def _kill_process_tree(proc: subprocess.Popen) -> None:
        """Kill the entire process group on Unix, or just the process on Windows."""
        try:
            if _IS_UNIX:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGKILL)
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
