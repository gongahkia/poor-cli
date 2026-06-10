import asyncio
from types import SimpleNamespace

from poor_cli.context_assembly import ContextFile, ContextSnapshot
from poor_cli.server.handlers.context import ContextHandlersMixin
from poor_cli.server.registry import REGISTRY


def _snapshot(*files: ContextFile) -> ContextSnapshot:
    return ContextSnapshot(
        system_prompt="system",
        rules="rules",
        files=files,
        messages=(),
        history=(),
        tool_schemas=(),
        tokens={"total": sum(file.tokens for file in files)},
        budget=1000,
        provider="test",
        model="test-model",
        key="key",
        user_prompt="inspect",
        turn_id="turn-1",
    )


class _Assembler:
    def __init__(self):
        self.calls = []

    async def assemble(self, **kwargs):
        self.calls.append(kwargs)
        files = [
            ContextFile(
                path=path,
                content="",
                tokens=10,
                reason="pinned",
                compressed=False,
            )
            for path in kwargs.get("pinned_context_files", [])
        ]
        return _snapshot(*files)


class _Server(ContextHandlersMixin):
    def __init__(self, core):
        self.core = core

    def _ensure_initialized(self):
        return None


def test_context_snapshot_serializes_snapshot(tmp_path):
    path = str(tmp_path / "app.py")
    core = SimpleNamespace(
        _context_pinned_files=[path],
        _context_dropped_files=set(),
        _last_context_snapshot=_snapshot(
            ContextFile(path=path, content="", tokens=42, reason="pagerank-hub", compressed=True),
        ),
    )
    result = asyncio.run(REGISTRY["context.snapshot"](_Server(core), {}))

    assert result["budget"] == 1000
    assert result["used"] == 42
    assert result["files"] == [
        {"path": path, "tokens": 42, "reason": "pinned", "compressed": True, "pinned": True}
    ]


def test_context_pin_drop_roundtrip_updates_next_refresh(tmp_path):
    path = str(tmp_path / "lib.py")
    assembler = _Assembler()
    core = SimpleNamespace(
        _context_assembly=assembler,
        _context_pinned_files=[],
        _context_dropped_files=set(),
        _last_context_snapshot=_snapshot(),
    )
    server = _Server(core)

    pinned = asyncio.run(REGISTRY["context.pin"](server, {"path": path}))
    assert pinned["pinned"] is True
    assert core._context_pinned_files == [path]
    assert assembler.calls[-1]["pinned_context_files"] == [path]
    assert pinned["files"][0]["pinned"] is True

    dropped = asyncio.run(REGISTRY["context.drop"](server, {"path": path}))
    assert dropped["dropped"] is True
    assert core._context_pinned_files == []
    assert path in core._context_dropped_files
    assert assembler.calls[-1]["pinned_context_files"] == []
