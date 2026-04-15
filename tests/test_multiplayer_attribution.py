import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from poor_cli.core_events import RepoHistoryAdapter
from poor_cli.multiplayer_attribution import (
    author_tag_for,
    current_author_tag,
    reset_current_author_tag,
    set_current_author_tag,
)
from poor_cli.repo_config import RepoConfig
from poor_cli.server.handlers.chat_streaming import ChatStreamingHandlersMixin


class _StreamingHarness(ChatStreamingHandlersMixin):
    def __init__(self, *, embedded: bool = False, capabilities=None) -> None:
        self._embedded_multiplayer_room = embedded
        self._client_capabilities = capabilities or {}


class MultiplayerAttributionTests(unittest.TestCase):
    def test_multi_user_author_tag_uses_matching_connection(self) -> None:
        session = SimpleNamespace(
            state=SimpleNamespace(
                members={
                    "conn-a": SimpleNamespace(client_name="Ada", role="prompter"),
                    "conn-b": SimpleNamespace(client_name="Ben", role="viewer"),
                }
            )
        )

        self.assertEqual(
            author_tag_for("conn-b", session),
            {
                "authorConnectionId": "conn-b",
                "authorDisplayName": "Ben",
                "authorRole": "viewer",
            },
        )

    def test_single_player_streaming_fallback_and_explicit_opt_out(self) -> None:
        tagged = _StreamingHarness()._with_chat_author({"requestId": "r-1"})
        self.assertEqual(tagged["authorConnectionId"], "local")
        self.assertTrue(tagged["authorDisplayName"])
        self.assertEqual(tagged["authorRole"], "local")

        opted_out = _StreamingHarness(
            capabilities={
                "multiplayer": {
                    "features": {
                        "messageAttribution": False,
                    }
                }
            }
        )._with_chat_author({"requestId": "r-2"})
        self.assertNotIn("authorConnectionId", opted_out)

    def test_repo_history_replay_preserves_author(self) -> None:
        author = {
            "authorConnectionId": "conn-a",
            "authorDisplayName": "Ada",
            "authorRole": "prompter",
        }
        with tempfile.TemporaryDirectory() as tmp:
            repo = RepoConfig(Path(tmp), enable_legacy_history_migration=False)
            repo.start_session(model="stub")
            adapter = RepoHistoryAdapter(repo)
            token = set_current_author_tag(author)
            try:
                adapter.add_message("user", "hello")
                adapter.add_message("model", "hi")
            finally:
                reset_current_author_tag(token)
            repo.end_session()

            replayed = RepoConfig(Path(tmp), enable_legacy_history_migration=False)
            self.assertEqual(len(replayed.sessions), 1)
            messages = replayed.sessions[0].messages
            self.assertEqual(messages[0].author, author)
            self.assertEqual(messages[1].author, author)
            self.assertEqual(current_author_tag()["authorConnectionId"], "local")


if __name__ == "__main__":
    unittest.main()
