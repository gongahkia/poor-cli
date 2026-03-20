import unittest
from types import SimpleNamespace

from poor_cli.multiplayer_session import AgendaItem, CollaborationSession, InviteToken


class MultiplayerSessionTests(unittest.TestCase):
    def make_member(self, connection_id: str, role: str, *, approved: bool = True) -> SimpleNamespace:
        return SimpleNamespace(
            connection_id=connection_id,
            client_name=connection_id,
            role=role,
            approved=approved,
            initialized=True,
            hand_raised=False,
            connected_at=1.0,
            last_active=1.0,
            joined_at="2026-03-18T00:00:00+00:00",
            closed=False,
        )

    def make_session(self) -> CollaborationSession:
        state = SimpleNamespace(
            name="dev",
            preset="mob",
            tokens={
                "tok-viewer": InviteToken(token="tok-viewer", role="viewer"),
                "tok-prompter": InviteToken(token="tok-prompter", role="prompter"),
            },
            members={
                "host": self.make_member("host", "prompter"),
                "guest": self.make_member("guest", "viewer"),
            },
            active_connection_id="host",
            lobby_enabled=True,
            agenda=[AgendaItem("a-1", "Inspect logs", "host", "2026-03-18T00:00:00+00:00")],
            activity=[],
            hand_raise_queue=[],
            next_agenda_id=2,
        )
        return CollaborationSession(
            state,
            is_member_closed=lambda member: getattr(member, "closed", False),
        )

    def test_handoff_next_driver_prefers_hand_raise_queue(self) -> None:
        session = self.make_session()
        result = session.set_member_hand_raised("guest", True)
        self.assertIsNotNone(result)

        next_driver = session.handoff_next_driver(actor_connection_id="host")
        self.assertEqual(next_driver, "guest")
        self.assertEqual(session.state.members["guest"].role, "prompter")
        self.assertEqual(session.state.members["host"].role, "viewer")

    def test_active_tokens_prunes_expired_entries(self) -> None:
        session = self.make_session()
        session.state.tokens["expired"] = InviteToken(
            token="expired",
            role="viewer",
            expires_at="2000-01-01T00:00:00+00:00",
        )

        tokens = session.active_tokens()
        self.assertEqual(tokens["viewer"], "tok-viewer")
        self.assertEqual(tokens["prompter"], "tok-prompter")
        self.assertNotIn("expired", session.state.tokens)

    def test_approve_room_member_promotes_pending_prompter(self) -> None:
        session = self.make_session()
        session.state.members["host"].role = "viewer"
        session.state.members["guest"].role = "prompter"
        session.state.members["guest"].approved = False

        approved, promoted = session.approve_room_member("guest")

        self.assertTrue(approved)
        self.assertEqual(promoted, "guest")
        self.assertTrue(session.state.members["guest"].approved)
        self.assertEqual(session.state.members["guest"].role, "prompter")
        self.assertEqual(session.state.members["host"].role, "viewer")

    def test_pop_room_member_promotes_fallback_and_clears_queue(self) -> None:
        session = self.make_session()
        session.state.members["guest"].hand_raised = True
        session.state.hand_raise_queue = ["guest"]

        member, promoted = session.pop_room_member("host", promote_fallback=True)

        self.assertIsNotNone(member)
        self.assertEqual(promoted, "guest")
        self.assertIsNone(session.state.active_connection_id)
        self.assertEqual(session.state.hand_raise_queue, [])
        self.assertEqual(session.state.members["guest"].role, "prompter")
        self.assertFalse(session.state.members["guest"].hand_raised)

    def test_rotate_room_token_replaces_role_token_and_revoke_removes_it(self) -> None:
        session = self.make_session()
        old_viewer_token = session.active_tokens()["viewer"]

        new_viewer_token = session.rotate_room_token("viewer", expires_in_seconds=60)

        self.assertNotEqual(new_viewer_token, old_viewer_token)
        self.assertNotIn(old_viewer_token, session.state.tokens)
        self.assertIn(new_viewer_token, session.state.tokens)
        self.assertEqual(session.state.tokens[new_viewer_token].role, "viewer")
        self.assertIsNotNone(session.state.tokens[new_viewer_token].expires_at)

        revoked = session.revoke_room_token(new_viewer_token)

        self.assertIsNotNone(revoked)
        self.assertEqual(revoked.token, new_viewer_token)
        self.assertNotIn(new_viewer_token, session.state.tokens)

    def test_set_room_lobby_off_approves_pending_members(self) -> None:
        session = self.make_session()
        session.state.members["guest"].approved = False
        session.state.members["guest"].role = "prompter"

        roles_rebalanced = session.set_room_lobby(False)

        self.assertTrue(roles_rebalanced)
        self.assertFalse(session.state.lobby_enabled)
        self.assertTrue(session.state.members["guest"].approved)
        self.assertEqual(session.state.members["host"].role, "prompter")
        self.assertEqual(session.state.members["guest"].role, "viewer")


if __name__ == "__main__":
    unittest.main()
