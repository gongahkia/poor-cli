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


if __name__ == "__main__":
    unittest.main()
