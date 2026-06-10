from poor_cli.plan_mode import PlanBoardStore


def test_plan_board_transitions_and_visible_history(tmp_path):
    store = PlanBoardStore(path=tmp_path / "plan_board.json")
    state = store.seed("plan-1", "summary", "request", ["read", "edit"])
    first = state["steps"][0]["id"]
    second = state["steps"][1]["id"]

    state = store.advance({"stepId": first})
    assert state["steps"][0]["status"] == "doing"
    state = store.advance({"stepId": first})
    assert state["steps"][0]["status"] == "done"
    state = store.block({"stepId": second})
    assert state["steps"][1]["status"] == "blocked"

    visible = {step["status"] for step in store.list()["steps"]}
    assert {"done", "blocked"} <= visible

    state = store.regress({"stepId": first})
    assert state["steps"][0]["status"] == "doing"
    state = store.regress({"stepId": second})
    assert state["steps"][1]["status"] == "todo"


def test_plan_board_persists_state(tmp_path):
    path = tmp_path / "plan_board.json"
    store = PlanBoardStore(path=path)
    state = store.seed("plan-1", "summary", "request", [{"description": "ship"}])
    step_id = state["steps"][0]["id"]
    store.advance({"stepId": step_id})
    store.add({"description": "verify"})

    reloaded = PlanBoardStore(path=path).list()
    assert reloaded["planId"] == "plan-1"
    assert [step["description"] for step in reloaded["steps"]] == ["ship", "verify"]
    assert reloaded["steps"][0]["status"] == "doing"
