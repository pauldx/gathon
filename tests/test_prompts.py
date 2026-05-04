"""Tests for gathon.prompts — MCP prompt templates."""

from gathon.prompts import (
    architecture_map_prompt,
    debug_issue_prompt,
    onboard_developer_prompt,
    pre_merge_check_prompt,
    review_changes_prompt,
)


def test_review_changes_default():
    msgs = review_changes_prompt()
    assert len(msgs) == 1
    assert msgs[0]["role"] == "user"
    assert "HEAD~1" in msgs[0]["content"]
    assert "detect_changes" in msgs[0]["content"]


def test_review_changes_custom_base():
    msgs = review_changes_prompt(base="main")
    assert "main" in msgs[0]["content"]


def test_architecture_map():
    msgs = architecture_map_prompt()
    assert len(msgs) == 1
    assert "architecture" in msgs[0]["content"].lower()
    assert "god_nodes" in msgs[0]["content"]


def test_debug_issue_default():
    msgs = debug_issue_prompt()
    assert "the reported issue" in msgs[0]["content"]


def test_debug_issue_custom():
    msgs = debug_issue_prompt(description="NullPointerException in auth")
    assert "NullPointerException" in msgs[0]["content"]


def test_onboard_developer():
    msgs = onboard_developer_prompt()
    assert "Onboard" in msgs[0]["content"]
    assert "get_minimal_context" in msgs[0]["content"]


def test_pre_merge_check_default():
    msgs = pre_merge_check_prompt()
    assert "HEAD~1" in msgs[0]["content"]
    assert "SAFE" in msgs[0]["content"]


def test_pre_merge_check_custom_base():
    msgs = pre_merge_check_prompt(base="develop")
    assert "develop" in msgs[0]["content"]


def test_all_prompts_return_list_of_dicts():
    for fn in [
        review_changes_prompt,
        architecture_map_prompt,
        debug_issue_prompt,
        onboard_developer_prompt,
        pre_merge_check_prompt,
    ]:
        result = fn()
        assert isinstance(result, list)
        for msg in result:
            assert isinstance(msg, dict)
            assert "role" in msg
            assert "content" in msg


def test_prompts_registered_in_server():
    from gathon.server import mcp
    prompts = mcp._prompt_manager._prompts
    expected = {
        "review_changes", "architecture_map",
        "debug_issue", "onboard_developer", "pre_merge_check",
    }
    missing = expected - set(prompts.keys())
    assert not missing, f"Missing prompts: {missing}"
