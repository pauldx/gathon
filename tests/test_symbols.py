"""Tests for tree-sitter symbol indexing engine."""

from __future__ import annotations

from gathon.symbols.indexer import SymbolIndex
from gathon.symbols.models import (
    SymbolInfo,
    compute_body_hash,
)
from gathon.symbols.parsers import _parse_python_regex, parse_file


class TestModels:
    def test_symbol_info_fields(self):
        s = SymbolInfo(
            name="foo", qualified_name="mod.foo", kind="function",
            file_path="test.py", line_start=1, line_end=5,
            language="python", signature="def foo(x: int) -> str",
        )
        assert s.name == "foo"
        assert s.kind == "function"

    def test_body_hash(self):
        h1 = compute_body_hash("  def foo():\n    pass")
        h2 = compute_body_hash("  def foo():\n    pass")
        h3 = compute_body_hash("  def bar():\n    pass")
        assert h1 == h2
        assert h1 != h3
        assert len(h1) == 16


class TestRegexParser:
    def test_parse_python_functions(self, tmp_path):
        src = tmp_path / "test.py"
        src.write_text(
            "def hello(name: str) -> str:\n"
            "    return f'Hello {name}'\n\n"
            "def world():\n"
            "    pass\n"
        )
        result = _parse_python_regex(str(src))
        assert result.language == "python"
        names = [s.name for s in result.symbols]
        assert "hello" in names
        assert "world" in names

    def test_parse_python_class(self, tmp_path):
        src = tmp_path / "test.py"
        src.write_text(
            "class MyClass(Base):\n"
            "    def method(self):\n"
            "        pass\n"
        )
        result = _parse_python_regex(str(src))
        names = [s.name for s in result.symbols]
        assert "MyClass" in names

    def test_parse_imports(self, tmp_path):
        src = tmp_path / "test.py"
        src.write_text(
            "import os\n"
            "from pathlib import Path\n"
            "from typing import (\n"
            "    Any,\n"
            "    Dict,\n"
            ")\n"
        )
        result = _parse_python_regex(str(src))
        modules = [i.module for i in result.imports]
        assert "os" in modules
        assert "pathlib" in modules


class TestParseFile:
    def test_python_file(self, tmp_path):
        src = tmp_path / "test.py"
        src.write_text("def greet():\n    print('hi')\n")
        result = parse_file(str(src))
        assert result.language == "python"
        assert len(result.symbols) >= 1

    def test_unknown_extension(self, tmp_path):
        src = tmp_path / "test.xyz"
        src.write_text("random content")
        result = parse_file(str(src))
        assert result.symbols == []

    def test_nonexistent_file(self):
        result = parse_file("/nonexistent/path.xyz")
        assert result.language == "unknown"
        assert result.symbols == []


class TestSymbolIndex:
    def test_index_and_find(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "main.py").write_text(
            "def hello():\n    return 'hello'\n\n"
            "class Greeter:\n    def greet(self):\n        pass\n"
        )
        idx = SymbolIndex(project_root=str(proj))
        idx.index_project(str(proj))
        results = idx.find_symbol("hello")
        assert len(results) >= 1
        assert results[0].name == "hello"
        idx.close()

    def test_find_class(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "models.py").write_text(
            "class User:\n    def __init__(self, name):\n        self.name = name\n"
        )
        idx = SymbolIndex(project_root=str(proj))
        idx.index_project(str(proj))
        results = idx.find_symbol("User", exact=True)
        assert len(results) >= 1
        idx.close()

    def test_get_function_source(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "funcs.py").write_text(
            "def add(a, b):\n    \"\"\"Add two numbers.\"\"\"\n    return a + b\n"
        )
        idx = SymbolIndex(project_root=str(proj))
        idx.index_project(str(proj))
        source = idx.get_function_source("add", level=0)
        assert "return a + b" in source
        idx.close()

    def test_stats(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        (proj / "a.py").write_text("def f1():\n    pass\ndef f2():\n    pass\n")
        idx = SymbolIndex(project_root=str(proj))
        idx.index_project(str(proj))
        s = idx.stats()
        assert s["symbol_count"] >= 2
        assert s["file_count"] >= 1
        idx.close()

    def test_empty_project(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        idx = SymbolIndex(project_root=str(proj))
        idx.index_project(str(proj))
        s = idx.stats()
        assert s["symbol_count"] == 0
        idx.close()

    def test_stale_files(self, tmp_path):
        proj = tmp_path / "proj"
        proj.mkdir()
        f = proj / "a.py"
        f.write_text("def old():\n    pass\n")
        idx = SymbolIndex(project_root=str(proj))
        idx.index_project(str(proj))
        # modify file to bump mtime
        import time
        time.sleep(0.05)
        f.write_text("def new_func():\n    pass\n")
        stale = idx.get_stale_files(str(proj))
        assert len(stale) >= 1
        idx.close()
