"""Tests for gathon.extract — orchestrator."""

from gathon.extract import extract_files
from gathon.store import UnifiedStore


def test_extract_code_file(tmp_path):
    db = tmp_path / "g.db"
    store = UnifiedStore(str(db))

    py = tmp_path / "hello.py"
    py.write_text("def greet(name):\n    return f'Hello {name}'\n")

    result = extract_files([py], store, tmp_path)
    assert result["total_files"] == 1
    assert "code_graph" in result["pipelines"]

    stats = store.get_unified_stats()
    assert stats["total_nodes"] > 0
    store.close()


def test_extract_config_file(tmp_path):
    db = tmp_path / "g.db"
    store = UnifiedStore(str(db))

    cfg = tmp_path / "app.yaml"
    cfg.write_text("server:\n  port: 8080\n")

    result = extract_files([cfg], store, tmp_path)
    assert "config_yaml" in result["pipelines"]

    stats = store.get_unified_stats()
    assert stats["total_nodes"] > 0
    store.close()


def test_extract_openapi_file(tmp_path):
    db = tmp_path / "g.db"
    store = UnifiedStore(str(db))

    spec = tmp_path / "api.yaml"
    spec.write_text(
        "openapi: '3.0.0'\ninfo:\n  title: T\n"
        "paths:\n  /foo:\n    get:\n      summary: Get foo\n"
    )

    result = extract_files([spec], store, tmp_path)
    assert "openapi_yaml" in result["pipelines"]
    store.close()


def test_extract_mixed_files(tmp_path):
    db = tmp_path / "g.db"
    store = UnifiedStore(str(db))

    py = tmp_path / "main.py"
    py.write_text("x = 1\n")
    md = tmp_path / "readme.md"
    md.write_text("# Hello\nWorld\n")
    cfg = tmp_path / "conf.json"
    cfg.write_text('{"key": "val"}')

    result = extract_files([py, md, cfg], store, tmp_path)
    assert result["total_files"] == 3
    assert len(result["pipelines"]) >= 2
    store.close()


def test_extract_skips_unchanged(tmp_path):
    db = tmp_path / "g.db"
    store = UnifiedStore(str(db))

    cfg = tmp_path / "app.yaml"
    cfg.write_text("port: 3000\n")

    extract_files([cfg], store, tmp_path)
    result2 = extract_files([cfg], store, tmp_path)
    assert result2["pipelines"]["config_yaml"]["parsed"] == 0
    store.close()


def test_extract_handles_bad_file(tmp_path):
    db = tmp_path / "g.db"
    store = UnifiedStore(str(db))

    bad = tmp_path / "broken.yaml"
    bad.write_text("{{{{not yaml")

    result = extract_files([bad], store, tmp_path)
    assert len(result["errors"]) >= 0
    store.close()
