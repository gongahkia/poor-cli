import unittest
from unittest.mock import patch

from poor_cli.__main__ import _run_preview_mode


class _FakePreviewServer:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.stop_called = False
        self._reload_pending = False
        self._watch_task = None

    async def start(self):
        return {"mode": self.mode, "message": f"{self.mode} started"}

    async def stop(self):
        self.stop_called = True
        return {"stopped": [self.mode]}

    def status(self):
        return {"running": True, "mode": self.mode, "reloadPending": False}

    async def health(self):
        return {"healthy": True, **self.status()}


class PreviewModeTests(unittest.TestCase):
    def test_static_mode_stops_cleanly_on_keyboard_interrupt(self) -> None:
        fake = _FakePreviewServer("static")
        with patch("poor_cli.preview_server.PreviewServer", return_value=fake):
            with patch("poor_cli.__main__.time.sleep", side_effect=KeyboardInterrupt):
                code = _run_preview_mode([])
        self.assertEqual(code, 0)
        self.assertTrue(fake.stop_called)

    def test_proxy_mode_stops_cleanly_on_keyboard_interrupt(self) -> None:
        fake = _FakePreviewServer("proxy")
        with patch("poor_cli.preview_server.PreviewServer", return_value=fake):
            with patch("poor_cli.__main__.time.sleep", side_effect=KeyboardInterrupt):
                code = _run_preview_mode([])
        self.assertEqual(code, 0)
        self.assertTrue(fake.stop_called)

    def test_stop_flag_calls_stop_without_wait_loop(self) -> None:
        fake = _FakePreviewServer("static")
        with patch("poor_cli.preview_server.PreviewServer", return_value=fake):
            code = _run_preview_mode(["--stop"])
        self.assertEqual(code, 0)
        self.assertTrue(fake.stop_called)


    def test_health_flag_prints_json(self) -> None:
        fake = _FakePreviewServer("static")
        with patch("poor_cli.preview_server.PreviewServer", return_value=fake):
            code = _run_preview_mode(["--health"])
        self.assertEqual(code, 0)


class PreviewServerUnitTests(unittest.TestCase):
    def test_status_includes_reload_version(self):
        from poor_cli.preview_server import PreviewServer
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            server = PreviewServer(root=td)
            s = server.status()
            self.assertIn("reloadVersion", s)
            self.assertEqual(s["reloadVersion"], 0)

    def test_health_returns_healthy_key(self):
        import asyncio
        from poor_cli.preview_server import PreviewServer
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            server = PreviewServer(root=td)
            h = asyncio.run(server.health())
            self.assertIn("healthy", h)
            self.assertFalse(h["healthy"]) # not started yet


if __name__ == "__main__":
    unittest.main()
