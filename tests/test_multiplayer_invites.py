import unittest

from poor_cli.multiplayer_invites import (
    build_signed_invite,
    decode_bridge_invite_payload,
    verify_signed_invite,
)


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

    def test_bridge_invite_requires_http_signaling_url(self) -> None:
        invite = build_signed_invite(
            {
                "signalingUrl": "wss://host.test/rpc",
                "sessionId": "dev",
                "role": "viewer",
                "token": "tok-789",
                "expiresAt": "2099-01-01T00:00:00+00:00",
            },
            secret="secret-123",
        )

        with self.assertRaisesRegex(
            ValueError, "Invite signaling URL must start with http:// or https://"
        ):
            decode_bridge_invite_payload(invite)


if __name__ == "__main__":
    unittest.main()
