from __future__ import annotations

from poor_cli.multiplayer import MultiplayerStore
from poor_cli.multiplayer_runtime import MultiplayerCommandRouter


def test_multiplayer_router_join_snapshot_and_queue(tmp_path):
    store = MultiplayerStore(tmp_path)
    host = store.host_session("Host")
    router = MultiplayerCommandRouter(store)

    joined = router.handle({"method": "join", "params": {"displayName": "Peer"}})
    assert joined["ok"] is True
    peer_id = joined["result"]["participant"]["participantId"]

    queued = router.handle(
        {
            "method": "queue.enqueue",
            "params": {
                "authorId": peer_id,
                "prompt": "review the queue",
            },
        }
    )
    assert queued["ok"] is True
    assert queued["result"]["queue"][0]["prompt"] == "review the queue"

    moved = router.handle(
        {
            "method": "queue.move",
            "params": {
                "actorId": host.participant_id,
                "itemId": queued["result"]["item"]["itemId"],
                "direction": "up",
            },
        }
    )
    assert moved["ok"] is True

    claimed = router.handle({"method": "queue.next", "params": {"actorId": host.participant_id}})
    assert claimed["ok"] is True
    assert claimed["result"]["item"]["status"] == "running"

    finished = router.handle(
        {
            "method": "queue.finish",
            "params": {
                "itemId": claimed["result"]["item"]["itemId"],
                "status": "completed",
            },
        }
    )
    assert finished["ok"] is True
    assert finished["result"]["item"]["status"] == "completed"

    snapshot = router.handle({"method": "snapshot"})
    assert snapshot["ok"] is True
    assert len(snapshot["result"]["participants"]) == 2
    assert len(snapshot["result"]["queue"]) == 0


def test_multiplayer_router_reports_validation_errors(tmp_path):
    router = MultiplayerCommandRouter(MultiplayerStore(tmp_path))

    response = router.handle({"method": "join", "params": {"displayName": "Peer"}})

    assert response["ok"] is False
    assert "no hosted multiplayer session" in response["error"]["message"]
