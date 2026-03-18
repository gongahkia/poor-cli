import unittest

from poor_cli.multiplayer_invites import build_signed_invite, verify_signed_invite


class MultiplayerInviteTests(unittest.TestCase):
    def test_signed_invite_round_trip(self) -> None:
        invite = build_signed_invite(
            {
                "signalingUrl": "https://host.test/rpc",
                "sessionId": "dev",
                "role": "prompter",
                "token": "tok-123",
                "expiresAt": "2099-01-01T00:00:00+00:00",
            },
            secret="secret-123",
        )

        payload = verify_signed_invite(invite, secret="secret-123")
        self.assertEqual(payload["signalingUrl"], "https://host.test/rpc")
        self.assertEqual(payload["sessionId"], "dev")
        self.assertEqual(payload["role"], "prompter")
        self.assertEqual(payload["token"], "tok-123")

    def test_signed_invite_rejects_wrong_secret(self) -> None:
        invite = build_signed_invite(
            {
                "signalingUrl": "https://host.test/rpc",
                "sessionId": "dev",
                "role": "viewer",
                "token": "tok-456",
                "expiresAt": "2099-01-01T00:00:00+00:00",
            },
            secret="secret-123",
        )

        with self.assertRaisesRegex(ValueError, "signature"):
            verify_signed_invite(invite, secret="wrong-secret")


if __name__ == "__main__":
    unittest.main()
