"""Tests for sandbox isolation engine."""

from __future__ import annotations

from gathon.sandbox.chunker import chunk_json, chunk_markdown, chunk_plaintext
from gathon.sandbox.content_store import ContentStore
from gathon.sandbox.executor import SandboxExecutor, SandboxResult, _find_runtime, _wrap_code
from gathon.sandbox.security import check_command


class TestSecurity:
    def test_allow_normal_command(self):
        allowed, reason = check_command("ls -la", "shell")
        assert allowed
        assert reason == ""

    def test_deny_rm_rf_root(self):
        allowed, reason = check_command("rm -rf /", "shell")
        assert not allowed
        assert "Blocked" in reason

    def test_deny_sudo(self):
        allowed, _ = check_command("sudo apt install foo", "shell")
        assert not allowed

    def test_deny_python_os_system(self):
        allowed, _ = check_command("os.system('rm -rf /')", "python")
        assert not allowed

    def test_allow_python_normal(self):
        allowed, _ = check_command("print('hello')", "python")
        assert allowed

    def test_deny_js_exec_sync(self):
        allowed, _ = check_command("execSync('rm -rf /')", "javascript")
        assert not allowed

    def test_chained_command_deny(self):
        allowed, _ = check_command("echo ok && sudo rm -rf /", "shell")
        assert not allowed

    def test_allow_normal_chained(self):
        allowed, _ = check_command("echo ok && ls -la", "shell")
        assert allowed


class TestChunker:
    def test_markdown_headers(self):
        md = "# Title\nIntro\n## Section 1\nContent 1\n## Section 2\nContent 2"
        chunks = chunk_markdown(md)
        assert len(chunks) >= 2
        titles = [c.title for c in chunks]
        assert "Title" in titles or any("Title" in t for t in titles)

    def test_markdown_code_block_atomic(self):
        md = "# Code\n```python\ndef foo():\n    pass\n```\n# Next"
        chunks = chunk_markdown(md)
        code_chunk = [c for c in chunks if "```" in c.content or "def foo" in c.content]
        assert len(code_chunk) >= 1

    def test_plaintext_paragraphs(self):
        text = "Para 1 content.\n\nPara 2 content.\n\nPara 3 content.\n\nPara 4."
        chunks = chunk_plaintext(text)
        assert len(chunks) >= 1

    def test_plaintext_short_fallback(self):
        text = "Line 1\nLine 2"
        chunks = chunk_plaintext(text)
        assert len(chunks) >= 1

    def test_json_simple(self):
        data = {"name": "test", "value": 42}
        chunks = chunk_json(data)
        assert len(chunks) >= 1

    def test_json_array_batching(self):
        data = [{"id": i, "data": "x" * 100} for i in range(50)]
        chunks = chunk_json(data)
        assert len(chunks) >= 1

    def test_json_nested(self):
        data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
        chunks = chunk_json(data)
        assert len(chunks) >= 1

    def test_empty_input(self):
        assert chunk_markdown("") == []
        assert chunk_plaintext("") == []


class TestContentStore:
    def test_index_and_search(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        content = "Python is a programming language for web dev"
        source_id = store.index("test doc", content)
        assert source_id > 0
        results = store.search("Python programming")
        assert len(results) >= 1
        assert any("Python" in r.snippet or "python" in r.snippet.lower() for r in results)
        store.close()

    def test_index_json(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        data = {"users": [{"name": "Alice", "role": "admin"}, {"name": "Bob", "role": "user"}]}
        source_id = store.index_json("users data", data)
        assert source_id > 0
        results = store.search("Alice admin")
        assert len(results) >= 1
        store.close()

    def test_search_no_results(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        results = store.search("nonexistent query terms")
        assert results == []
        store.close()

    def test_purge(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        store.index("doc1", "some content here")
        stats_before = store.stats()
        assert stats_before["source_count"] == 1
        store.purge()
        stats_after = store.stats()
        assert stats_after["source_count"] == 0
        assert stats_after["chunk_count"] == 0
        store.close()

    def test_stats(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        s = store.stats()
        assert s["source_count"] == 0
        assert s["chunk_count"] == 0
        assert s["total_bytes"] == 0
        store.close()

    def test_context_manager(self, tmp_path):
        with ContentStore(tmp_path / "test.db") as store:
            store.index("test", "content")
            s = store.stats()
            assert s["source_count"] == 1


class TestExecutor:
    def test_find_runtime_python(self):
        rt = _find_runtime("python")
        assert rt is not None
        assert "python" in rt

    def test_find_runtime_shell(self):
        rt = _find_runtime("shell")
        assert rt is not None

    def test_find_runtime_unknown(self):
        rt = _find_runtime("cobol")
        assert rt is None

    def test_wrap_go(self):
        code = 'fmt.Println("hello")'
        wrapped = _wrap_code("go", code)
        assert "func main()" in wrapped
        assert "package main" in wrapped

    def test_wrap_php(self):
        code = 'echo "hello";'
        wrapped = _wrap_code("php", code)
        assert "<?php" in wrapped

    def test_no_wrap_python(self):
        code = "print('hello')"
        wrapped = _wrap_code("python", code)
        assert wrapped == code

    def test_execute_python(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        executor = SandboxExecutor(content_store=store)
        result = executor.execute("python", "print('hello sandbox')")
        assert result.exit_code == 0
        assert "hello sandbox" in result.stdout
        assert result.language == "python"
        assert result.elapsed_ms >= 0

    def test_execute_shell(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        executor = SandboxExecutor(content_store=store)
        result = executor.execute("shell", "echo 'test output'")
        assert result.exit_code == 0
        assert "test output" in result.stdout

    def test_execute_error(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        executor = SandboxExecutor(content_store=store)
        result = executor.execute("python", "import nonexistent_module_xyz")
        assert result.exit_code != 0
        assert result.stderr

    def test_execute_denied(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        executor = SandboxExecutor(content_store=store)
        result = executor.execute("shell", "sudo rm -rf /")
        assert result.exit_code != 0
        assert "Blocked" in result.stderr

    def test_execute_unknown_language(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        executor = SandboxExecutor(content_store=store)
        result = executor.execute("brainfuck", "++++++++++")
        assert result.exit_code != 0

    def test_batch_execute(self, tmp_path):
        store = ContentStore(tmp_path / "test.db")
        executor = SandboxExecutor(content_store=store)
        results = executor.batch_execute([
            {"language": "python", "code": "print(1+1)"},
            {"language": "shell", "code": "echo hello"},
        ])
        assert len(results) == 2
        assert results[0].exit_code == 0
        assert "2" in results[0].stdout
        assert results[1].exit_code == 0

    def test_sandbox_result_dataclass(self):
        r = SandboxResult(
            stdout="ok", stderr="", exit_code=0,
            language="python", elapsed_ms=10,
            raw_bytes=100, context_bytes=50,
        )
        assert r.raw_bytes == 100
        assert r.context_bytes == 50
