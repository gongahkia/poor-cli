"""
Tests for conversation history management
"""

import pytest
import tempfile
from pathlib import Path
from poor_cli.history import HistoryManager, Message, Session, TokenCounter


class TestTokenCounter:
    """Test token counting"""

    def test_estimate_tokens(self):
        """Test token estimation"""
        # Empty string
        assert TokenCounter.estimate_tokens("") == 0

        # Short text (~4 chars per token)
        assert TokenCounter.estimate_tokens("hello") > 0

        # Longer text
        text = "This is a longer text that should have more tokens"
        tokens = TokenCounter.estimate_tokens(text)
        assert tokens >= len(text) // 5  # At least 1 token per 5 chars

    def test_estimate_messages_tokens(self):
        """Test message list token estimation"""
        messages = [
            {"content": "Hello"},
            {"content": "How are you?"},
            {"parts": ["I'm good"]},
        ]

        total = TokenCounter.estimate_messages_tokens(messages)
        assert total > 0
        assert total > len(messages) * 10  # At least overhead per message


class TestMessage:
    """Test Message dataclass"""

    def test_message_creation(self):
        """Test creating a message"""
        msg = Message(
            role="user",
            content="Test message",
            timestamp="2024-01-01T00:00:00",
            tokens=10
        )

        assert msg.role == "user"
        assert msg.content == "Test message"
        assert msg.tokens == 10

    def test_message_to_dict(self):
        """Test message serialization"""
        msg = Message(
            role="model",
            content="Response",
            timestamp="2024-01-01T00:00:00",
            tokens=5
        )

        msg_dict = msg.to_dict()
        assert msg_dict["role"] == "model"
        assert msg_dict["content"] == "Response"

    def test_message_from_dict(self):
        """Test message deserialization"""
        msg_dict = {
            "role": "user",
            "content": "Test",
            "timestamp": "2024-01-01T00:00:00",
            "tokens": 3,
            "metadata": None
        }

        msg = Message.from_dict(msg_dict)
        assert msg.role == "user"
        assert msg.content == "Test"


class TestSession:
    """Test Session dataclass"""

    def test_session_creation(self):
        """Test creating a session"""
        session = Session(
            session_id="test_123",
            started_at="2024-01-01T00:00:00"
        )

        assert session.session_id == "test_123"
        assert session.messages == []
        assert session.total_tokens == 0

    def test_session_to_dict(self):
        """Test session serialization"""
        session = Session(
            session_id="test_456",
            started_at="2024-01-01T00:00:00",
            total_tokens=100
        )
        session.messages.append(Message(
            role="user",
            content="Hi",
            timestamp="2024-01-01T00:00:00"
        ))

        session_dict = session.to_dict()
        assert session_dict["session_id"] == "test_456"
        assert session_dict["total_tokens"] == 100
        assert len(session_dict["messages"]) == 1


class TestHistoryManager:
    """Test history manager"""

    def test_init_database(self):
        """Test database initialization"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            assert db_path.exists()

    def test_start_session(self):
        """Test starting a new session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            session = manager.start_session("test-model")
            assert session is not None
            assert session.model == "test-model"
            assert manager.current_session == session

    def test_add_message(self):
        """Test adding messages to session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            manager.start_session()
            msg = manager.add_message("user", "Hello")

            assert msg.role == "user"
            assert msg.content == "Hello"
            assert msg.tokens > 0
            assert len(manager.current_session.messages) == 1

    def test_get_recent_messages(self):
        """Test retrieving recent messages"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            manager.start_session()
            manager.add_message("user", "Message 1")
            manager.add_message("model", "Response 1")
            manager.add_message("user", "Message 2")

            # Get all messages
            messages = manager.get_recent_messages()
            assert len(messages) == 3

            # Get limited messages
            messages = manager.get_recent_messages(limit=2)
            assert len(messages) == 2
            assert messages[0].content == "Response 1"

    def test_end_session(self):
        """Test ending a session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            session = manager.start_session()
            session_id = session.session_id

            manager.add_message("user", "Test")
            manager.end_session()

            assert manager.current_session is None

            # Should be able to load it
            loaded_session = manager.get_session_history(session_id)
            assert loaded_session is not None
            assert len(loaded_session.messages) == 1

    def test_prune_history(self):
        """Test history pruning"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            manager.start_session()

            # Add many messages
            for i in range(10):
                manager.add_message("user", "Test message " * 100)

            initial_count = len(manager.current_session.messages)
            initial_tokens = manager.current_session.total_tokens

            # Prune to low limit
            removed = manager.prune_history(max_tokens=100)

            assert removed > 0
            assert len(manager.current_session.messages) < initial_count
            assert manager.current_session.total_tokens <= 100

    def test_list_sessions(self):
        """Test listing sessions"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            # Create multiple sessions
            manager.start_session()
            manager.add_message("user", "Test 1")
            manager.end_session()

            manager.start_session()
            manager.add_message("user", "Test 2")
            manager.end_session()

            sessions = manager.list_sessions(limit=10)
            assert len(sessions) >= 2

    def test_export_session(self):
        """Test session export to JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            session = manager.start_session()
            session_id = session.session_id
            manager.add_message("user", "Test export")
            manager.end_session()

            # Export session
            export_path = Path(tmpdir) / "export.json"
            manager.export_session(session_id, export_path)

            assert export_path.exists()

            # Verify it's valid JSON
            import json
            with open(export_path) as f:
                data = json.load(f)

            assert data["session_id"] == session_id
            assert len(data["messages"]) == 1

    def test_get_total_tokens(self):
        """Test getting total token count"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            assert manager.get_total_tokens() == 0

            manager.start_session()
            manager.add_message("user", "Test")

            assert manager.get_total_tokens() > 0

    def test_clear_current_session(self):
        """Test clearing current session"""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "history.db"
            manager = HistoryManager(db_path)

            manager.start_session()
            manager.add_message("user", "Test")
            manager.add_message("model", "Response")

            assert len(manager.current_session.messages) == 2

            manager.clear_current_session()

            assert len(manager.current_session.messages) == 0
            assert manager.current_session.total_tokens == 0
