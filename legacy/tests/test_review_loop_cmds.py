from poor_cli.cli.review_cmds import build_review_loop_prompt


def test_review_loop_prompt_keeps_single_writer_contract():
    prompt = build_review_loop_prompt("diff --git a/a.py b/a.py")
    assert "clean-context code review loop" in prompt
    assert "Do not edit files" in prompt
    assert "findings first" in prompt
