"""Tests for gathon.router — file extension dispatch."""

from pathlib import Path

from gathon.router import route_file, route_files
from gathon.schema import Pipeline


def test_code_extensions():
    for ext in [".py", ".ts", ".tsx", ".js", ".go", ".rs", ".java", ".sh", ".ipynb"]:
        assert route_file(Path(f"test{ext}")) == Pipeline.CODE_GRAPH, f"Failed for {ext}"


def test_doc_extensions():
    for ext in [".md", ".mdx", ".txt", ".rst", ".html"]:
        assert route_file(Path(f"test{ext}")) == Pipeline.GATHON_DOC, f"Failed for {ext}"


def test_paper_extension():
    assert route_file(Path("paper.pdf")) == Pipeline.GATHON_PDF


def test_office_extensions():
    assert route_file(Path("doc.docx")) == Pipeline.GATHON_OFFICE
    assert route_file(Path("sheet.xlsx")) == Pipeline.GATHON_OFFICE


def test_image_extensions():
    for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
        assert route_file(Path(f"img{ext}")) == Pipeline.GATHON_IMAGE, f"Failed for {ext}"


def test_video_extensions():
    for ext in [".mp4", ".mov", ".webm", ".mp3", ".wav"]:
        assert route_file(Path(f"media{ext}")) == Pipeline.GATHON_VIDEO, f"Failed for {ext}"


def test_config_yaml(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("key: value\n")
    assert route_file(f) == Pipeline.CONFIG_YAML


def test_openapi_yaml(tmp_path):
    f = tmp_path / "api.yaml"
    f.write_text("openapi: 3.0.0\ninfo:\n  title: Test\n")
    assert route_file(f) == Pipeline.OPENAPI_YAML


def test_unknown_falls_to_doc():
    assert route_file(Path("mystery.xyz")) == Pipeline.GATHON_DOC


def test_route_files_groups():
    files = [Path("a.py"), Path("b.ts"), Path("readme.md"), Path("img.png")]
    groups = route_files(files)
    assert Pipeline.CODE_GRAPH in groups
    assert len(groups[Pipeline.CODE_GRAPH]) == 2
    assert Pipeline.GATHON_DOC in groups
    assert Pipeline.GATHON_IMAGE in groups
