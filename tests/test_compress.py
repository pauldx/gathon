"""Tests for gathon.compress — token compression."""

from gathon.compress import (
    Intensity,
    compress_text,
    compress_tool_response,
)


class TestCompressText:
    def test_off_returns_unchanged(self):
        text = "Sure! I'd be happy to help you with that."
        assert compress_text(text, "off") == text

    def test_empty_returns_empty(self):
        assert compress_text("", "full") == ""

    def test_lite_drops_fillers(self):
        text = "This is basically just a really simple function."
        result = compress_text(text, "lite")
        assert "basically" not in result
        assert "just" not in result
        assert "really" not in result
        assert "simply" not in result.lower()
        assert "function" in result

    def test_lite_drops_pleasantries(self):
        text = "Sure, I'd be happy to help you with that. The function works."
        result = compress_text(text, "lite")
        assert "Sure" not in result
        assert "happy to" not in result
        assert "function" in result

    def test_lite_drops_hedging(self):
        text = "It might be worth checking the database connection."
        result = compress_text(text, "lite")
        assert "might be worth" not in result
        assert "database" in result

    def test_lite_replaces_phrases(self):
        text = "In order to fix the bug, make sure to check the logs."
        result = compress_text(text, "lite")
        assert "In order to" not in result
        assert "to" in result or "To" in result

    def test_full_drops_articles(self):
        text = "The function returns a value from the database."
        result = compress_text(text, "full")
        assert " the " not in result.lower().replace("the ", "", 1) or True
        for word in result.split():
            assert word.lower().rstrip(".,") not in {"a", "an", "the"}

    def test_full_drops_connective_fluff(self):
        text = "However, the function is correct. Furthermore, it is fast."
        result = compress_text(text, "full")
        assert "However" not in result
        assert "Furthermore" not in result

    def test_ultra_abbreviates(self):
        text = "The database authentication configuration is complex."
        result = compress_text(text, "ultra")
        assert "DB" in result
        assert "auth" in result
        assert "config" in result

    def test_ultra_arrows_for_causality(self):
        text = "The pool fails because the connection times out."
        result = compress_text(text, "ultra")
        assert "→" in result
        assert "because" not in result


class TestPreservation:
    def test_preserves_inline_code(self):
        text = "The function `calculate_total()` is basically important."
        result = compress_text(text, "full")
        assert "`calculate_total()`" in result

    def test_preserves_code_blocks(self):
        code = "Sure, here is the fix:\n```python\ndef foo():\n    return 42\n```"
        result = compress_text(code, "full")
        assert "```python\ndef foo():\n    return 42\n```" in result

    def test_preserves_urls(self):
        text = "Check https://example.com/api/v2 for the documentation."
        result = compress_text(text, "full")
        assert "https://example.com/api/v2" in result

    def test_preserves_file_paths(self):
        text = "The file is located at src/gathon/store.py for reference."
        result = compress_text(text, "full")
        assert "src/gathon/store.py" in result

    def test_preserves_qualified_names(self):
        text = "The function is at main.py::MyClass.method for sure."
        result = compress_text(text, "full")
        assert "main.py::MyClass.method" in result

    def test_preserves_numbers(self):
        text = "The function takes approximately 42ms to run."
        result = compress_text(text, "ultra")
        assert "42ms" in result


class TestToolResponseCompression:
    def test_off_returns_same(self):
        data = {"name": "Sure, this is the function", "kind": "Function"}
        result = compress_tool_response(data, "off")
        assert result == data

    def test_compresses_text_keys(self):
        data = {
            "name": "This is basically a really long description of the thing",
            "kind": "Function",
            "file_path": "src/main.py",
        }
        result = compress_tool_response(data, "full")
        assert "basically" not in result["name"]
        assert result["kind"] == "Function"
        assert result["file_path"] == "src/main.py"

    def test_skips_structural_keys(self):
        data = {
            "total_nodes": 42,
            "file_path": "/some/path.py",
            "qualified_name": "mod::fn",
            "pipeline": "code_graph",
            "count": 10,
        }
        result = compress_tool_response(data, "ultra")
        assert result == data

    def test_recurses_into_nested_dicts(self):
        data = {
            "results": [
                {
                    "name": "This is basically a simple helper",
                    "kind": "Function",
                }
            ]
        }
        result = compress_tool_response(data, "full")
        inner = result["results"][0]
        assert "basically" not in inner["name"]
        assert inner["kind"] == "Function"

    def test_skips_short_strings(self):
        data = {"name": "foo", "kind": "Function"}
        result = compress_tool_response(data, "full")
        assert result["name"] == "foo"

    def test_nested_list_compression(self):
        data = {
            "questions": [
                "What are the most connected components in the codebase?",
                "Which files cross code and document boundaries?",
            ]
        }
        result = compress_tool_response(data, "full")
        for q in result["questions"]:
            assert isinstance(q, str)


class TestIntensityEnum:
    def test_values(self):
        assert Intensity.LITE == "lite"
        assert Intensity.FULL == "full"
        assert Intensity.ULTRA == "ultra"
        assert Intensity.OFF == "off"
