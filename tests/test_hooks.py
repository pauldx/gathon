"""Tests for gathon.hooks — hook installation and generation."""

import json

from gathon.hooks import (
    HOOKS_JSON,
    POST_CHECKOUT_HOOK,
    POST_COMMIT_HOOK,
    PRE_COMMIT_HOOK,
    generate_hooks_json,
    install_hooks,
)


def test_hooks_json_structure():
    assert "hooks" in HOOKS_JSON
    assert "PostToolUse" in HOOKS_JSON["hooks"]
    assert "SessionStart" in HOOKS_JSON["hooks"]


def test_hook_scripts_are_shell():
    for script in [PRE_COMMIT_HOOK, POST_COMMIT_HOOK, POST_CHECKOUT_HOOK]:
        assert script.startswith("#!/bin/sh\n")
        assert "gathon" in script


def test_generate_hooks_json():
    output = generate_hooks_json()
    parsed = json.loads(output)
    assert parsed == HOOKS_JSON


def test_install_hooks_creates_claude_dir(tmp_path):
    result = install_hooks(tmp_path)
    hooks_path = tmp_path / ".claude" / "hooks.json"
    assert hooks_path.exists()
    parsed = json.loads(hooks_path.read_text())
    assert "hooks" in parsed
    assert any("Wrote" in m for m in result["messages"])


def test_install_hooks_skips_git_hooks_no_dir(tmp_path):
    result = install_hooks(tmp_path)
    assert any("skipped git hooks" in m for m in result["messages"])


def test_install_hooks_creates_git_hooks(tmp_path):
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)

    result = install_hooks(tmp_path)
    for name in ["pre-commit", "post-commit", "post-checkout"]:
        hook = git_hooks / name
        assert hook.exists()
        assert hook.stat().st_mode & 0o111  # executable
    assert any("Installed" in m for m in result["messages"])


def test_install_hooks_skips_existing(tmp_path):
    git_hooks = tmp_path / ".git" / "hooks"
    git_hooks.mkdir(parents=True)
    (git_hooks / "pre-commit").write_text("#!/bin/sh\necho existing\n")

    result = install_hooks(tmp_path)
    assert any("Skipped pre-commit" in m for m in result["messages"])
    assert (git_hooks / "pre-commit").read_text() == "#!/bin/sh\necho existing\n"
