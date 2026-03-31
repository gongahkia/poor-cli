import unittest
from unittest.mock import patch

from poor_cli.__main__ import _run_preview_mode


class _FakePreviewServer:
    def __init__(self, mode: str) -> None:
        self.mode = mode
        self.stop_called = False

    async def start(self):
        return {"mode": self.mode, "message": f"{self.mode} started"}

    async def stop(self):
        self.stop_called = True
        return {"stopped": [self.mode]}

    def status(self):
        return {"running": True, "mode": self.mode}


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


if __name__ == "__main__":
    unittest.main()
