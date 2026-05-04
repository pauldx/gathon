"""Tests for breaking change detection and program slicer."""

from __future__ import annotations

from gathon.tools.breaking_changes import (
    _compare_symbols,
    _extract_go_symbols,
    _extract_js_symbols,
    _extract_python_symbols,
)
from gathon.tools.slicer import _build_def_use_chains, _find_enclosing_control, backward_slice


class TestPythonExtractor:
    def test_extract_function(self):
        source = (
            "def hello(name: str, greeting: str = 'Hi') -> str:\n"
            "    return f'{greeting} {name}'\n"
        )
        symbols = _extract_python_symbols(source)
        assert "hello" in symbols
        assert symbols["hello"]["kind"] == "function"
        assert "name" in symbols["hello"]["params"]

    def test_extract_class(self):
        source = "class MyClass(Base):\n    def method(self):\n        pass\n"
        symbols = _extract_python_symbols(source)
        assert "MyClass" in symbols
        assert symbols["MyClass"]["kind"] == "class"
        assert "method" in symbols["MyClass"]["methods"]

    def test_skip_private(self):
        source = "def _private():\n    pass\ndef public():\n    pass\n"
        symbols = _extract_python_symbols(source)
        assert "_private" not in symbols
        assert "public" in symbols

    def test_syntax_error(self):
        symbols = _extract_python_symbols("def broken(\n")
        assert symbols == {}


class TestJSExtractor:
    def test_extract_exports(self):
        source = "export function fetchData() {}\nexport class ApiClient {}\n"
        symbols = _extract_js_symbols(source)
        assert "fetchData" in symbols
        assert "ApiClient" in symbols

    def test_module_exports(self):
        source = "module.exports = MyApp\n"
        symbols = _extract_js_symbols(source)
        assert "MyApp" in symbols


class TestGoExtractor:
    def test_exported_funcs(self):
        source = "func HandleRequest(w http.ResponseWriter) {}\nfunc private() {}\n"
        symbols = _extract_go_symbols(source)
        assert "HandleRequest" in symbols
        assert "private" not in symbols


def _func_sym(params=None, defaults=0):
    return {
        "kind": "function", "params": params or ["x"],
        "defaults": defaults, "return_type": None,
        "bases": [], "methods": {},
    }


class TestCompareSymbols:
    def test_removed_function(self):
        old = {"foo": _func_sym()}
        new = {}
        changes = _compare_symbols(old, new, "test.py")
        assert len(changes) >= 1
        assert changes[0]["kind"] == "removed_function"

    def test_removed_parameter(self):
        old = {"foo": _func_sym(["x", "y"])}
        new = {"foo": _func_sym(["x"])}
        changes = _compare_symbols(old, new, "test.py")
        assert any(c["kind"] == "removed_parameter" for c in changes)

    def test_added_required_param(self):
        old = {"foo": _func_sym(["x"])}
        new = {"foo": _func_sym(["x", "y"])}
        changes = _compare_symbols(old, new, "test.py")
        assert any(c["kind"] == "added_required_param" for c in changes)

    def test_no_changes(self):
        sym = {"foo": _func_sym()}
        changes = _compare_symbols(sym, sym, "test.py")
        assert len(changes) == 0


class TestSlicer:
    def test_simple_slice(self, tmp_path):
        src = tmp_path / "test.py"
        src.write_text(
            "a = 1\n"
            "b = 2\n"
            "c = a + b\n"
            "d = 42\n"
            "result = c * 2\n"
        )
        result = backward_slice(str(src), "result", 5)
        assert 5 in result["slice_lines"]
        assert 3 in result["slice_lines"]  # c = a + b
        assert 1 in result["slice_lines"]  # a = 1
        assert 2 in result["slice_lines"]  # b = 2
        # d = 42 should NOT be in slice
        assert 4 not in result["slice_lines"]
        assert result["reduction_pct"] > 0

    def test_control_flow(self, tmp_path):
        src = tmp_path / "test.py"
        src.write_text(
            "x = 10\n"
            "if x > 5:\n"
            "    y = x * 2\n"
            "else:\n"
            "    y = 0\n"
            "result = y\n"
        )
        result = backward_slice(str(src), "result", 6)
        assert 6 in result["slice_lines"]
        assert 2 in result["slice_lines"]  # if statement (enclosing control)

    def test_nonexistent_file(self):
        result = backward_slice("/nonexistent.py", "x", 1)
        assert "error" in result

    def test_empty_file(self, tmp_path):
        src = tmp_path / "empty.py"
        src.write_text("")
        result = backward_slice(str(src), "x", 1)
        assert result["slice_size"] == 0

    def test_syntax_error_fallback(self, tmp_path):
        src = tmp_path / "bad.py"
        src.write_text("def broken(\nx = 1\nresult = x\n")
        result = backward_slice(str(src), "x", 3)
        assert result.get("fallback") is True
        assert result["slice_size"] > 0

    def test_build_def_use_chains(self):
        import ast
        source = "x = 1\ny = x + 2\nz = y\n"
        tree = ast.parse(source)
        defs, uses = _build_def_use_chains(tree)
        assert "x" in defs
        assert "y" in defs
        assert 2 in uses  # line 2 uses 'x'

    def test_find_enclosing_control(self):
        import ast
        source = "x = 1\nif x > 0:\n    y = x\n"
        tree = ast.parse(source)
        enclosing = _find_enclosing_control(tree, 3)
        assert 2 in enclosing  # if statement encloses line 3
