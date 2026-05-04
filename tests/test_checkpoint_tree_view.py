from poor_cli.tui.checkpoint_tree import checkpoint_tree_payload, diff_hunk_count


def test_checkpoint_tree_payload_combines_branch_and_checkpoint_nodes():
    branch_tree = {
        "activeId": "turn-1",
        "roots": [
            {
                "id": "turn-1",
                "label": "user: start",
                "active": True,
                "createdAt": "2026-01-01",
                "preview": "start",
                "children": [],
            }
        ],
    }
    checkpoints = [
        {
            "checkpointId": "cp-1",
            "createdAt": "2026-01-02",
            "description": "manual",
            "operationType": "manual",
        }
    ]

    payload = checkpoint_tree_payload("session-1", branch_tree, checkpoints)

    assert payload["kind"] == "session"
    assert payload["children"][0]["kind"] == "branch"
    assert payload["children"][1]["kind"] == "checkpoint"
    assert payload["children"][1]["id"] == "cp-1"


def test_diff_hunk_count_for_fixture_diff():
    diff = """--- a/demo.py
+++ b/demo.py
@@ -1,2 +1,2 @@
-old
+new
@@ -10,1 +10,1 @@
-a
+b
"""

    assert diff_hunk_count(diff) == 2
