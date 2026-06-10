from types import SimpleNamespace

import poor_cli.repo_config as repo_config_module
from poor_cli.server.handlers.sessions import SessionsHandlersMixin


class _Server(SessionsHandlersMixin):
    def __init__(self, *, auto_migrate: bool):
        self.core = SimpleNamespace(
            config=SimpleNamespace(
                history=SimpleNamespace(
                    auto_migrate_legacy_history=auto_migrate,
                )
            )
        )


def test_get_repo_config_uses_top_level_repo_config(monkeypatch):
    sentinel = object()
    captured = {}

    def fake_get_repo_config(*, enable_legacy_history_migration):
        captured["auto_migrate"] = enable_legacy_history_migration
        return sentinel

    monkeypatch.setattr(repo_config_module, "get_repo_config", fake_get_repo_config)

    server = _Server(auto_migrate=False)

    assert server._get_repo_config() is sentinel
    assert captured == {"auto_migrate": False}
