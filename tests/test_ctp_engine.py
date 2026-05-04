"""Tests for CTP engine: dispatch, matching, telemetry."""

from __future__ import annotations

from unittest.mock import patch

from gathon.cli_token_parse import FilterResult
from gathon.cli_token_parse.engine import (
    FILTER_REGISTRY,
    _strip_env_prefix,
    filter_command,
    has_filter,
    load_filters,
)


class TestRegistration:
    def setup_method(self):
        load_filters()

    def test_filters_registered(self):
        names = [r.name for r in FILTER_REGISTRY]
        assert "git_status" in names
        assert "git_log" in names
        assert "git_diff" in names
        assert "git_add" in names
        assert "git_commit" in names
        assert "git_push" in names
        assert "pytest" in names
        assert "grep" in names
        assert "ls" in names
        assert "cat" in names
        assert "docker_ps" in names

    def test_has_filter_git(self):
        assert has_filter("git status")
        assert has_filter("git log -10")
        assert has_filter("git diff HEAD~1")
        assert has_filter("git add .")
        assert has_filter("git commit -m 'test'")
        assert has_filter("git push origin main")

    def test_has_filter_tools(self):
        assert has_filter("pytest tests/")
        assert has_filter("grep -rn foo .")
        assert has_filter("rg pattern src/")
        assert has_filter("ls -la")
        assert has_filter("cat README.md")
        assert has_filter("docker ps")

    def test_no_filter_unknown(self):
        assert not has_filter("echo hello")
        assert not has_filter("make build")
        assert not has_filter("ssh user@host")


class TestEnvPrefix:
    def test_strip_single(self):
        assert _strip_env_prefix("FOO=bar git status") == "git status"

    def test_strip_multiple(self):
        assert _strip_env_prefix("A=1 B=2 ls") == "ls"

    def test_no_prefix(self):
        assert _strip_env_prefix("git status") == "git status"


class TestFilterCommand:
    def setup_method(self):
        load_filters()

    @patch("gathon.cli_token_parse.engine.run_command")
    def test_passthrough_unknown(self, mock_run):
        mock_run.return_value = ("hello world\n", "", 0)
        result = filter_command("echo hello")
        assert result.filter_name == "passthrough"
        assert result.output == "hello world\n"
        assert result.exit_code == 0
        assert result.before_tokens == result.after_tokens

    @patch("gathon.cli_token_parse.engine.run_command")
    @patch("gathon.cli_token_parse.filters.git_status.run_command")
    def test_git_status_filtered(self, mock_filter_run, mock_engine_run):
        mock_engine_run.return_value = (
            "On branch main\nnothing to commit\n", "", 0,
        )
        mock_filter_run.return_value = ("## main\n", "", 0)
        result = filter_command("git status")
        assert result.filter_name == "git_status"
        assert "main" in result.output

    def test_result_dataclass(self):
        r = FilterResult(
            output="ok", exit_code=0, filter_name="test",
            before_tokens=100, after_tokens=30,
        )
        assert r.savings_pct == 70.0

    def test_result_zero_before(self):
        r = FilterResult(
            output="", exit_code=0, filter_name="test",
            before_tokens=0, after_tokens=0,
        )
        assert r.savings_pct == 0.0
