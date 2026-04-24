from __future__ import annotations

import pytest

from poor_cli.exceptions import ValidationError
from poor_cli.multiplayer import MultiplayerStore


def test_host_and_peer_queue_reordering(tmp_path):
    store = MultiplayerStore(tmp_path)
    host = store.host_session("Host")
    peer = store.join_session("Peer")

    first = store.enqueue_prompt(host.participant_id, "first")
    second = store.enqueue_prompt(peer.participant_id, "second")
    third = store.enqueue_prompt(peer.participant_id, "third")

    assert [item.item_id for item in store.list_queue()] == [
        first.item_id,
        second.item_id,
        third.item_id,
    ]

    with pytest.raises(ValidationError, match="host privileges"):
        store.move_queue_item(peer.participant_id, third.item_id, "up")

    moved = store.move_queue_item(host.participant_id, third.item_id, "up")

    assert moved.item_id == third.item_id
    assert [item.item_id for item in store.list_queue()] == [
        first.item_id,
        third.item_id,
        second.item_id,
    ]


def test_author_or_host_can_edit_queued_prompt(tmp_path):
    store = MultiplayerStore(tmp_path)
    host = store.host_session("Host")
    alice = store.join_session("Alice")
    bob = store.join_session("Bob")

    item = store.enqueue_prompt(alice.participant_id, "draft one")

    with pytest.raises(ValidationError, match="author or host"):
        store.update_queued_prompt(bob.participant_id, item.item_id, "bad edit")

    updated = store.update_queued_prompt(alice.participant_id, item.item_id, "draft two")
    assert updated.prompt == "draft two"

    host_updated = store.update_queued_prompt(host.participant_id, item.item_id, "host edit")
    assert host_updated.prompt == "host edit"


def test_task_thread_merge_requires_template_approval(tmp_path):
    store = MultiplayerStore(tmp_path)
    host = store.host_session("Host")
    alice = store.join_session("Alice")
    bob = store.join_session("Bob")

    template = store.upsert_approval_template(
        host.participant_id,
        "PRD review",
        ["prd", "merge"],
        required_count=2,
        required_people=[alice.participant_id, bob.participant_id],
    )
    thread = store.create_thread(alice.participant_id, "Draft voice PRD")
    store.add_thread_event(
        thread.thread_id,
        alice.participant_id,
        "comment",
        "Initial PRD notes",
    )
    merge = store.create_merge_request(
        thread.thread_id,
        alice.participant_id,
        "Merge PRD summary",
        context_summary="Decision summary",
        template_id=template.template_id,
    )

    with pytest.raises(ValidationError, match="approval requirements"):
        store.merge_thread(host.participant_id, merge.merge_id)

    store.record_approval(
        alice.participant_id,
        "merge",
        merge.merge_id,
        template.template_id,
    )
    status = store.approval_status("merge", merge.merge_id, template.template_id)
    assert status["satisfied"] is False

    store.record_approval(
        bob.participant_id,
        "merge",
        merge.merge_id,
        template.template_id,
    )
    status = store.approval_status("merge", merge.merge_id, template.template_id)
    assert status["satisfied"] is True

    merged = store.merge_thread(host.participant_id, merge.merge_id)
    assert merged.status == "merged"
    assert store.list_threads()[0].status == "merged"


def test_named_template_blocks_non_eligible_approver(tmp_path):
    store = MultiplayerStore(tmp_path)
    host = store.host_session("Host")
    alice = store.join_session("Alice")
    bob = store.join_session("Bob")

    template = store.upsert_approval_template(
        host.participant_id,
        "Named approver",
        ["plan"],
        required_count=1,
        required_people=[alice.participant_id],
    )

    with pytest.raises(ValidationError, match="not eligible"):
        store.record_approval(
            bob.participant_id,
            "plan",
            "plan-1",
            template.template_id,
        )

    approval = store.record_approval(
        alice.participant_id,
        "plan",
        "plan-1",
        template.template_id,
    )
    assert approval["decision"] == "approved"
