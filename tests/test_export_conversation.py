import asyncio
from types import SimpleNamespace

from poor_cli.repo_config import ChatMessage
from poor_cli.server.handlers.sessions import SessionsHandlersMixin


class _Server(SessionsHandlersMixin):
    def __init__(self, repo):
        self._repo = repo
        self.core = SimpleNamespace(
            config=SimpleNamespace(model=SimpleNamespace(provider="test", model_name="model"))
        )

    def _ensure_initialized(self):
        return None

    def _get_repo_config(self):
        return self._repo


def _repo():
    messages = [
        ChatMessage(role="user", content="hello", timestamp="2026-04-14T00:00:00"),
        ChatMessage(role="assistant", content="world", timestamp="2026-04-14T00:00:01"),
    ]
    return SimpleNamespace(
        current_session=SimpleNamespace(session_id="session-abcdef123456"),
        get_recent_messages=lambda count: messages,
    )


def test_export_conversation_writes_all_formats_to_output_dir(tmp_path):
    server = _Server(_repo())
    out_dir = tmp_path / "exports"
    cases = {
        "markdown": ".md",
        "json": ".json",
        "transcript": ".transcript",
    }

    for fmt, suffix in cases.items():
        result = asyncio.run(
            server.handle_export_conversation({"format": fmt, "outputDir": str(out_dir)})
        )
        path = out_dir / result["filePath"].split("/")[-1]
        assert path.exists()
        assert path.suffix == suffix
        assert "hello" in path.read_text(encoding="utf-8")
