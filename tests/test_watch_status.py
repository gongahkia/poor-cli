import asyncio
from types import SimpleNamespace

from poor_cli.config import Config
from poor_cli.server.handlers.watch import WatchHandlersMixin


class WatchServer(WatchHandlersMixin):
    pass


def test_watch_status_rpc_shape(tmp_path):
    (tmp_path / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "ignored.py").write_text("print('skip')\n", encoding="utf-8")
    config = Config()
    config.agentic.auto_lint = True
    server = WatchServer()
    server.core = SimpleNamespace(config=config)

    result = asyncio.run(server.handle_watch_status({"root": str(tmp_path), "limit": 20}))

    assert result["qa_enabled"] is True
    assert isinstance(result["recent_actions"], list)
    assert {"watches", "qa_enabled", "recent_actions"} <= set(result)
    by_name = {watch["path"].split("/")[-1]: watch for watch in result["watches"]}
    assert by_name["app.py"]["ignored"] is False
    assert by_name["ignored.py"]["ignored"] is True
    assert by_name["ignored.py"]["last_match"] == "ignored.py"
