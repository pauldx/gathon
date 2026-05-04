"""Tests for CTP filter functions with fixture data."""

from __future__ import annotations

from gathon.cli_token_parse.filters.cat_filter import filter_cat
from gathon.cli_token_parse.filters.docker_filter import _compact_ports, _short_image
from gathon.cli_token_parse.filters.git_diff import _compact_diff
from gathon.cli_token_parse.filters.git_log import _parse_commits, _truncate_lines
from gathon.cli_token_parse.filters.git_ops import filter_git_commit, filter_git_push
from gathon.cli_token_parse.filters.git_status import _filter_verbose, _parse_porcelain
from gathon.cli_token_parse.filters.grep_filter import _compact_path, filter_grep
from gathon.cli_token_parse.filters.ls_filter import _human_size
from gathon.cli_token_parse.filters.pytest_filter import _parse_summary, filter_pytest


class TestGitStatus:
    def test_clean(self):
        result = _parse_porcelain("## main\n")
        assert "clean" in result
        assert "main" in result

    def test_staged_files(self):
        porcelain = "## main\nM  foo.py\nA  bar.py\n"
        result = _parse_porcelain(porcelain)
        assert "Staged: 2 files" in result
        assert "foo.py" in result

    def test_modified_files(self):
        porcelain = "## dev\n M readme.md\n"
        result = _parse_porcelain(porcelain)
        assert "Modified: 1 files" in result

    def test_untracked(self):
        porcelain = "## main\n?? new.txt\n?? tmp/\n"
        result = _parse_porcelain(porcelain)
        assert "Untracked: 2 files" in result

    def test_conflicts(self):
        porcelain = "## main\nUU conflict.py\n"
        result = _parse_porcelain(porcelain)
        assert "Conflicts: 1 files" in result

    def test_verbose_strips_hints(self):
        text = (
            'On branch main\n'
            '  (use "git add" to update)\n'
            '\n'
            'modified: foo.py\n'
        )
        result = _filter_verbose(text)
        assert "use \"git add\"" not in result
        assert "modified: foo.py" in result

    def test_empty(self):
        result = _parse_porcelain("")
        assert "clean" in result


class TestGitLog:
    def test_parse_commits(self):
        text = (
            "abc1234 Fix bug (2h ago) <dev>\n"
            "Some body line\n"
            "BREAKING CHANGE: removed old api\n"
            "---END---\n"
            "def5678 Add feature (1d ago) <dev>\n"
            "---END---\n"
        )
        result = _parse_commits(text)
        assert "abc1234" in result
        assert "def5678" in result
        assert "BREAKING" in result

    def test_truncate_lines(self):
        long_line = "x" * 200
        result = _truncate_lines(long_line, 80)
        assert len(result.splitlines()[0]) == 80

    def test_empty_log(self):
        result = _parse_commits("")
        assert "No commits" in result


class TestGitDiff:
    def test_compact_diff(self):
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "index abc..def 100644\n"
            "--- a/foo.py\n"
            "+++ b/foo.py\n"
            "@@ -1,3 +1,4 @@ def main():\n"
            " existing\n"
            "+new line\n"
            "-old line\n"
        )
        result = _compact_diff(diff, "foo.py | 2 +-")
        assert "foo.py" in result
        assert "+new line" in result or "new line" in result

    def test_empty_diff(self):
        result = _compact_diff("", "")
        assert "No diff" in result


class TestGitOps:
    def test_commit_parses_hash(self):
        stdout = "[main abc1234] Fix something\n 1 file changed\n"
        result = filter_git_commit(stdout, "", ["git", "commit"])
        assert "ok abc1234" in result

    def test_commit_nothing(self):
        result = filter_git_commit(
            "", "nothing to commit, working tree clean",
            ["git", "commit"],
        )
        assert "nothing to commit" in result

    def test_push_up_to_date(self):
        result = filter_git_push(
            "", "Everything up-to-date\n", ["git", "push"],
        )
        assert "up-to-date" in result


class TestPytest:
    def test_all_pass(self):
        stdout = (
            "============================= test session starts ==============================\n"
            "collected 42 items\n"
            "tests/test_foo.py ...........................................\n"
            "============================== 42 passed in 1.23s =============================\n"
        )
        result = filter_pytest(stdout, "", ["pytest"])
        assert "42 passed" in result
        assert "FAIL" not in result

    def test_with_failures(self):
        stdout = (
            "============================= test session starts ==============================\n"
            "collected 10 items\n"
            "============================= FAILURES ========================================\n"
            "_____________________________ test_bad __________________________________________\n"
            "tests/test_foo.py::test_bad\n"
            "> assert False\n"
            "E assert False\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/test_foo.py::test_bad - AssertionError\n"
            "========================= 1 failed, 9 passed in 2.0s =========================\n"
        )
        result = filter_pytest(stdout, "", ["pytest"])
        assert "1 failed" in result
        assert "9 passed" in result
        assert "FAIL" in result

    def test_no_tests(self):
        result = filter_pytest("", "", ["pytest"])
        assert "No tests collected" in result

    def test_parse_summary(self):
        counts = _parse_summary("5 passed, 2 failed, 1 skipped in 3.5s")
        assert counts["passed"] == 5
        assert counts["failed"] == 2
        assert counts["skipped"] == 1


class TestGrep:
    def test_grouped(self):
        stdout = (
            "src/main.py:10:def foo():\n"
            "src/main.py:20:def bar():\n"
            "src/lib.py:5:import foo\n"
        )
        result = filter_grep(stdout, "", ["grep", "foo", "."])
        assert "3 matches in 2F" in result
        assert "[file] src/main.py (2)" in result
        assert "[file] src/lib.py (1)" in result

    def test_no_matches(self):
        result = filter_grep("", "", ["grep", "nonexistent", "."])
        assert "0 matches" in result

    def test_compact_path(self):
        short = "src/foo.py"
        assert _compact_path(short) == short
        long = "very/long/deeply/nested/path/to/some/really/deep/file.py"
        compact = _compact_path(long)
        assert len(compact) < len(long)
        assert "..." in compact


class TestLs:
    def test_human_size(self):
        assert _human_size(100) == "100B"
        assert _human_size(2048) == "2.0K"
        assert _human_size(1048576) == "1.0M"


class TestCat:
    def test_short_file(self):
        content = "\n".join(f"line {i}" for i in range(50))
        result = filter_cat(content, "", ["cat", "file.py"])
        assert result == content

    def test_long_file_truncated(self):
        content = "\n".join(f"line {i}" for i in range(500))
        result = filter_cat(content, "", ["cat", "file.py"])
        assert "lines omitted" in result
        assert "line 0" in result
        assert "line 499" in result

    def test_empty(self):
        result = filter_cat("", "", ["cat", "file.py"])
        assert "empty" in result


class TestDocker:
    def test_short_image(self):
        assert _short_image("library/nginx") == "nginx"
        assert _short_image("nginx") == "nginx"
        assert _short_image("gcr.io/project/app") == "app"

    def test_compact_ports(self):
        assert _compact_ports("") == ""
        assert _compact_ports("0.0.0.0:8080->80/tcp") == "8080"
        p = "0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp, 0.0.0.0:8080->8080/tcp"
        result = _compact_ports(p)
        assert "80" in result
        assert "443" in result
        assert "+1" in result
