import unittest

from poor_cli.multiplayer import MultiplayerHost
from poor_cli.multiplayer_invites import verify_signed_invite


class _StubRoomServer:
    def __init__(self) -> None:
        self.write_message_stdio = None


class MultiplayerHostTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.host = MultiplayerHost(
            bind_host="127.0.0.1",
            port=8765,
            room_names=["dev"],
            server_factory=_StubRoomServer,
            message_cls=object,
            rpc_error_cls=object,
            invite_secret="secret-123",
            owner_name="tester",
            ice_servers=[{"urls": ["stun:stun1.example.test:3478"]}],
        )

    async def asyncTearDown(self) -> None:
        await self.host.stop()

    async def test_build_room_share_payload_builds_canonical_signed_invite(self) -> None:
        share_payload = self.host.build_room_share_payload(
            "dev",
            "prompter",
            signaling_url="https://host.test/rpc",
            expires_in_seconds=60,
        )

        self.assertIsNotNone(share_payload)
        decoded = verify_signed_invite(
            str((share_payload or {}).get("inviteCode", "")),
            secret="secret-123",
            expected_session_id="dev",
            expected_role="prompter",
        )
        self.assertEqual(decoded["signalingUrl"], "https://host.test/rpc")
        self.assertEqual(decoded["token"], share_payload["token"])
        self.assertEqual(
            decoded["iceServers"],
            [{"urls": ["stun:stun1.example.test:3478"]}],
        )
        self.assertEqual(share_payload["ownerName"], "tester")
        self.assertTrue(str(share_payload["expiresAt"]).strip())


if __name__ == "__main__":
    unittest.main()
