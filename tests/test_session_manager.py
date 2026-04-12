"""tests for poor_cli.session_manager module."""

import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from poor_cli.session_manager import SessionManager, SessionState
from poor_cli.exceptions import ValidationError


class TestSessionManager(unittest.TestCase):
    def _make_mgr(self, max_sessions=8):
        with patch("poor_cli.session_manager.PoorCLICore"):
            return SessionManager(max_sessions=max_sessions)

    def test_create_session(self):
        mgr = self._make_mgr()
        s = mgr.create_session(label="test")
        self.assertEqual(s.label, "test")
        self.assertEqual(s.status, "active")
        self.assertTrue(s.session_id.startswith("sess-"))

    def test_default_session_set_on_first_create(self):
        mgr = self._make_mgr()
        s1 = mgr.create_session(label="first")
        self.assertEqual(mgr.default_session.session_id, s1.session_id)

    def test_get_session_by_id(self):
        mgr = self._make_mgr()
        s = mgr.create_session(label="a")
        found = mgr.get_session(s.session_id)
        self.assertEqual(found.session_id, s.session_id)

    def test_get_session_default_fallback(self):
        mgr = self._make_mgr()
        s = mgr.create_session(label="a")
        found = mgr.get_session(None)
        self.assertEqual(found.session_id, s.session_id)

    def test_get_session_no_sessions_raises(self):
        mgr = self._make_mgr()
        with self.assertRaises(ValidationError):
            mgr.get_session()

    def test_destroy_session(self):
        mgr = self._make_mgr()
        s = mgr.create_session(label="a")
        mgr.destroy_session(s.session_id)
        self.assertEqual(mgr.session_count, 0)

    def test_destroy_unknown_raises(self):
        mgr = self._make_mgr()
        with self.assertRaises(ValidationError):
            mgr.destroy_session("nonexistent")

    def test_destroy_default_promotes_next(self):
        mgr = self._make_mgr()
        s1 = mgr.create_session(label="a")
        s2 = mgr.create_session(label="b")
        mgr.destroy_session(s1.session_id)
        self.assertEqual(mgr.default_session.session_id, s2.session_id)

    def test_switch_default(self):
        mgr = self._make_mgr()
        s1 = mgr.create_session(label="a")
        s2 = mgr.create_session(label="b")
        mgr.switch_default(s2.session_id)
        self.assertEqual(mgr.default_session.session_id, s2.session_id)

    def test_switch_unknown_raises(self):
        mgr = self._make_mgr()
        with self.assertRaises(ValidationError):
            mgr.switch_default("nonexistent")

    def test_list_sessions(self):
        mgr = self._make_mgr()
        mgr.create_session(label="a")
        mgr.create_session(label="b")
        sessions = mgr.list_sessions()
        self.assertEqual(len(sessions), 2)
        labels = {s["label"] for s in sessions}
        self.assertEqual(labels, {"a", "b"})
        defaults = [s for s in sessions if s["isDefault"]]
        self.assertEqual(len(defaults), 1)

    def test_fork_session(self):
        mgr = self._make_mgr()
        s1 = mgr.create_session(label="origin", cwd="/tmp/work")
        forked = mgr.fork_session(s1.session_id, label="fork")
        self.assertEqual(forked.label, "fork")
        self.assertEqual(forked.working_directory, "/tmp/work")
        self.assertNotEqual(forked.session_id, s1.session_id)

    def test_fork_unknown_raises(self):
        mgr = self._make_mgr()
        with self.assertRaises(ValidationError):
            mgr.fork_session("nonexistent")

    def test_max_sessions_enforced(self):
        mgr = self._make_mgr(max_sessions=2)
        mgr.create_session(label="a")
        mgr.create_session(label="b")
        with self.assertRaises(ValidationError):
            mgr.create_session(label="c")

    def test_session_to_dict(self):
        mgr = self._make_mgr()
        s = mgr.create_session(label="test", cwd="/tmp")
        d = s.to_dict()
        self.assertEqual(d["label"], "test")
        self.assertEqual(d["workingDirectory"], "/tmp")
        self.assertEqual(d["status"], "active")
        self.assertIn("sessionId", d)
        self.assertIn("createdAt", d)

    def test_permission_callback_propagated(self):
        mgr = self._make_mgr()
        cb = AsyncMock()
        mgr.set_permission_callback(cb)
        s = mgr.create_session(label="new")
        self.assertEqual(s.core.permission_callback, cb)


if __name__ == "__main__":
    unittest.main()
