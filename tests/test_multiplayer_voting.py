import asyncio
import unittest
from types import SimpleNamespace

from poor_cli.edit_staging import EditStage
from poor_cli.multiplayer_session import CollaborationSession
from poor_cli.multiplayer_voting import HunkVote, HunkVoteNotApprovedError, VoteLedger, VoteStatus
from poor_cli.server.runtime import PoorCLIServer
from poor_cli.server.types import JsonRpcMessage


class VotingMembers:
    def __init__(self, *connection_ids: str):
        self.members = {connection_id: True for connection_id in connection_ids}

    def connected(self):
        return [connection_id for connection_id, connected in self.members.items() if connected]


def vote(connection_id: str, decision: str) -> HunkVote:
    return HunkVote(
        connection_id=connection_id,
        display_name=connection_id,
        decision=decision,  # type: ignore[arg-type]
        at=1.0,
    )


class MultiplayerVotingTests(unittest.TestCase):
    def test_majority_approve(self) -> None:
        members = VotingMembers("a", "b", "c")
        ledger = VoteLedger(threshold="majority", voter_ids=members.connected)

        ledger.record("h1", vote("a", "approve"))
        ledger.record("h1", vote("b", "approve"))
        ledger.record("h1", vote("c", "reject"))

        self.assertEqual(ledger.status("h1"), VoteStatus.APPROVED)

    def test_majority_borderline_pending(self) -> None:
        members = VotingMembers("a", "b")
        ledger = VoteLedger(threshold="majority", voter_ids=members.connected)

        ledger.record("h1", vote("a", "approve"))
        ledger.record("h1", vote("b", "reject"))

        self.assertEqual(ledger.status("h1"), VoteStatus.PENDING)

    def test_unanimous_approves_when_all_connected_approve(self) -> None:
        members = VotingMembers("a", "b", "c")
        ledger = VoteLedger(threshold="unanimous", voter_ids=members.connected)

        ledger.record("h1", vote("a", "approve"))
        ledger.record("h1", vote("b", "approve"))
        ledger.record("h1", vote("c", "approve"))

        self.assertEqual(ledger.status("h1"), VoteStatus.APPROVED)

    def test_owner_only_records_without_affecting_status(self) -> None:
        members = VotingMembers("a", "b", "c")
        ledger = VoteLedger(threshold="owner_only", voter_ids=members.connected)

        ledger.record("h1", vote("a", "approve"))
        ledger.record("h1", vote("b", "approve"))

        self.assertEqual(ledger.status("h1"), VoteStatus.PENDING)
        self.assertEqual(len(ledger.votes_for("h1")), 2)

    def test_disconnect_during_vote_recomputes_against_connected_members(self) -> None:
        members = VotingMembers("a", "b", "c")
        ledger = VoteLedger(threshold="majority", voter_ids=members.connected)
        ledger.record("h1", vote("a", "approve"))
        ledger.record("h1", vote("b", "approve"))

        self.assertEqual(ledger.status("h1"), VoteStatus.APPROVED)

        members.members["b"] = False

        self.assertEqual(ledger.status("h1"), VoteStatus.PENDING)

    def test_clear_vote_recomputes_status(self) -> None:
        members = VotingMembers("a", "b", "c")
        ledger = VoteLedger(threshold="majority", voter_ids=members.connected)
        ledger.record("h1", vote("a", "approve"))
        ledger.record("h1", vote("b", "approve"))

        self.assertEqual(ledger.status("h1"), VoteStatus.APPROVED)

        ledger.clear("h1", "b")

        self.assertEqual(ledger.status("h1"), VoteStatus.PENDING)
        self.assertEqual(len(ledger.votes_for("h1")), 1)

    def test_accept_hunk_rejected_when_vote_pending(self) -> None:
        stage = EditStage()
        edit = stage.stage(path="x.txt", original="a\n", proposed="b\n")
        hunk_id = edit.hunks[0].hunk_id
        member = SimpleNamespace(
            connection_id="a",
            client_name="a",
            role="prompter",
            approved=True,
            ws=SimpleNamespace(closed=False),
        )
        room = SimpleNamespace(
            members={"a": member, "b": SimpleNamespace(**{**member.__dict__, "connection_id": "b"})},
            hunk_vote_ledgers={},
            diff_voting_enabled=True,
            diff_voting_threshold="majority",
            diff_voting_required_voters=0,
        )
        room.session = CollaborationSession(room, is_member_closed=lambda item: item.ws.closed)
        room.session.ensure_vote_ledger(edit.edit_id).record(hunk_id, vote("a", "approve"))

        server = PoorCLIServer()
        server.initialized = True
        server.core = SimpleNamespace(
            tool_registry=SimpleNamespace(edit_stage=stage),
            checkpoint_manager=None,
            config=None,
        )
        server._multiplayer_room = room

        response = asyncio.run(server.dispatch(JsonRpcMessage(
            id=1,
            method="poor-cli/acceptHunk",
            params={"editId": edit.edit_id, "hunkId": hunk_id},
        )))

        self.assertEqual(response.error["code"], HunkVoteNotApprovedError.RPC_CODE)
        self.assertEqual(response.error["data"]["error_code"], "HunkVoteNotApproved")


if __name__ == "__main__":
    unittest.main()
