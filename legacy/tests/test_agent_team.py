import threading

from poor_cli.agent_team import AgentTeam, TeamScratchpad


def test_concurrent_writes_serialize_correctly(tmp_path):
    scratchpad = TeamScratchpad(team_id="team-test", path=tmp_path / "scratchpad.json")

    def write(name):
        scratchpad.post_message(name, "info", f"message from {name}")

    threads = [threading.Thread(target=write, args=(f"agent-{idx}",)) for idx in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(scratchpad.messages) == 2
    assert (tmp_path / "scratchpad.json").is_file()


def test_to_context_truncates_oldest_messages_first():
    scratchpad = TeamScratchpad(team_id="team-test")
    scratchpad.write_section("plan", "keep this section")
    for idx in range(40):
        scratchpad.post_message(f"a{idx}", "info", "x" * 80)

    context = scratchpad.to_context(max_tokens=80)

    assert "keep this section" in context
    assert "a0" not in context
    assert "a39" in context


def test_persistence_round_trip_preserves_messages_and_sections(tmp_path):
    path = tmp_path / "teams" / "team-a" / "scratchpad.json"
    scratchpad = TeamScratchpad(team_id="team-a", path=path)
    scratchpad.write_section("plan", "do it")
    scratchpad.post_message("planner", "decision", "go")

    loaded = TeamScratchpad.load(path)

    assert loaded.sections == {"plan": "do it"}
    assert loaded.messages[0].author_agent == "planner"
    assert loaded.messages[0].role == "decision"


def test_demo_team_run_writes_plan_progress_review(tmp_path):
    team = AgentTeam(tmp_path, team_id="demo")

    scratchpad = team.run_stub("ship phase D2")

    assert set(scratchpad.sections) == {"plan", "progress", "review"}
    assert [message.role for message in scratchpad.messages] == ["decision", "info", "decision"]
    assert (tmp_path / ".poor-cli" / "teams" / "demo" / "events.ndjson").is_file()
