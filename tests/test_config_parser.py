"""Tests for gathon.multimodal_graph.config_parser."""

from gathon.multimodal_graph.config_parser import parse_config


def test_parse_yaml(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("database:\n  host: localhost\n  port: 5432\napp:\n  debug: true\n")
    nodes, edges = parse_config(f)

    kinds = {n.kind for n in nodes}
    assert "ConfigFile" in kinds
    assert "ConfigKey" in kinds

    key_names = {n.name for n in nodes if n.kind == "ConfigKey"}
    assert "database" in key_names
    assert "host" in key_names
    assert "port" in key_names
    assert "app" in key_names
    assert "debug" in key_names

    contains = [e for e in edges if e.kind == "CONTAINS"]
    assert len(contains) >= 4


def test_parse_json(tmp_path):
    f = tmp_path / "config.json"
    f.write_text('{"server": {"port": 8080}, "debug": false}')
    nodes, edges = parse_config(f)
    key_names = {n.name for n in nodes if n.kind == "ConfigKey"}
    assert "server" in key_names
    assert "port" in key_names
    assert "debug" in key_names


def test_parse_toml(tmp_path):
    f = tmp_path / "config.toml"
    f.write_text('[database]\nhost = "localhost"\nport = 5432\n')
    nodes, edges = parse_config(f)
    key_names = {n.name for n in nodes if n.kind == "ConfigKey"}
    assert "database" in key_names
    assert "host" in key_names


def test_empty_config(tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text("---\n")
    nodes, edges = parse_config(f)
    assert nodes == []


def test_leaf_node_label(tmp_path):
    f = tmp_path / "app.yaml"
    f.write_text("timeout: 30\n")
    nodes, edges = parse_config(f)
    leaf = [n for n in nodes if n.name == "timeout"][0]
    assert "30" in leaf.label
