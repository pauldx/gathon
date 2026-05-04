"""Tests for gathon.cli — Click CLI commands."""

from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from gathon.cli import cli

runner = CliRunner()


def test_version():
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "gathon" in result.output.lower() or "version" in result.output.lower()


def test_status_no_db(tmp_path):
    result = runner.invoke(cli, ["status", str(tmp_path)])
    assert result.exit_code == 0
    assert "No graph found" in result.output


def test_update_no_db(tmp_path):
    result = runner.invoke(cli, ["update", str(tmp_path)])
    assert result.exit_code == 1
    assert "No graph.db found" in result.output


def test_export_no_db(tmp_path):
    result = runner.invoke(cli, ["export", str(tmp_path)])
    assert result.exit_code == 1
    assert "No graph found" in result.output


@patch("gathon.incremental.full_build", return_value={"total_files": 5, "errors": []})
@patch("gathon.store.UnifiedStore")
def test_build_full(mock_store_cls, mock_build, tmp_path):
    mock_store = MagicMock()
    mock_store.get_unified_stats.return_value = {
        "total_nodes": 10,
        "total_edges": 5,
        "files_count": 3,
    }
    mock_store_cls.return_value = mock_store

    result = runner.invoke(cli, ["build", str(tmp_path), "--full"])
    assert result.exit_code == 0
    assert "Full build" in result.output
    assert "10 nodes" in result.output
    mock_build.assert_called_once()
    mock_store.close.assert_called_once()


@patch("gathon.incremental.incremental_update", return_value={"total_files": 2})
@patch("gathon.store.UnifiedStore")
def test_build_incremental(mock_store_cls, mock_incr, tmp_path):
    mock_store = MagicMock()
    mock_store.get_unified_stats.return_value = {
        "total_nodes": 8,
        "total_edges": 3,
        "files_count": 2,
    }
    mock_store_cls.return_value = mock_store

    result = runner.invoke(cli, ["build", str(tmp_path)])
    assert result.exit_code == 0
    assert "Incremental update" in result.output
    mock_incr.assert_called_once()


@patch("gathon.hooks.install_hooks", return_value={"messages": ["Wrote hooks"]})
def test_install(mock_install, tmp_path):
    result = runner.invoke(cli, ["install", str(tmp_path)])
    assert result.exit_code == 0
    assert "Install complete" in result.output
    mock_install.assert_called_once()


def test_status_with_db(tmp_path):
    from gathon.store import UnifiedStore

    gathon_dir = tmp_path / ".gathon"
    gathon_dir.mkdir()
    store = UnifiedStore(str(gathon_dir / "graph.db"))
    store.close()

    result = runner.invoke(cli, ["status", str(tmp_path)])
    assert result.exit_code == 0
    assert "Nodes:" in result.output
    assert "Edges:" in result.output
