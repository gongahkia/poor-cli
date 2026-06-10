"""Tests for auto-memory distillation (heuristic + LLM)."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, MagicMock

from poor_cli.auto_memory import (
    extract_memories_from_history,
    extract_memories_with_llm,
    _generate_name,
    _MAX_MEMORIES_PER_SESSION,
)


class TestHeuristicExtraction(unittest.TestCase):
    def test_preference_signal_detected(self):
        msgs = [{"role": "user", "content": "I always prefer dark mode in editors"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].type, "feedback")

    def test_user_role_signal(self):
        msgs = [{"role": "user", "content": "I'm a backend engineer working on microservices"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].type, "user")

    def test_project_signal(self):
        msgs = [{"role": "user", "content": "Our release deadline is next Friday"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].type, "project")

    def test_reference_signal(self):
        msgs = [{"role": "user", "content": "Bugs are tracked in Linear project BACKEND"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].type, "reference")

    def test_assistant_messages_skipped(self):
        msgs = [{"role": "assistant", "content": "I always prefer to read files first"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 0)

    def test_short_messages_skipped(self):
        msgs = [{"role": "user", "content": "hi"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 0)

    def test_dedup_against_existing(self):
        msgs = [{"role": "user", "content": "I always prefer dark mode in editors"}]
        name = _generate_name("I always prefer dark mode in editors", "feedback")
        memories = extract_memories_from_history(msgs, existing_names={name.lower()})
        self.assertEqual(len(memories), 0)

    def test_max_cap(self):
        msgs = [{"role": "user", "content": f"I always prefer option {i} for everything"} for i in range(20)]
        memories = extract_memories_from_history(msgs)
        self.assertLessEqual(len(memories), _MAX_MEMORIES_PER_SESSION)

    def test_one_memory_per_message(self):
        msgs = [{"role": "user", "content": "I'm a developer and I always prefer vim. Our deadline is Friday. Tracked in Jira."}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 1) # first matching signal wins

    def test_no_signals_no_memories(self):
        msgs = [{"role": "user", "content": "Can you read the file at src/main.py?"}]
        memories = extract_memories_from_history(msgs)
        self.assertEqual(len(memories), 0)


class TestNameGeneration(unittest.TestCase):
    def test_short_name(self):
        name = _generate_name("Use Docker for deployment", "feedback")
        self.assertTrue(len(name) <= 60)
        self.assertTrue(len(name) >= 5)

    def test_strips_code_blocks(self):
        name = _generate_name("```python\nprint('hello')\n```\nActual content here", "feedback")
        self.assertNotIn("```", name)

    def test_truncates_at_sentence(self):
        name = _generate_name("First sentence. Second sentence that is much longer.", "user")
        self.assertNotIn("Second", name)

    def test_fallback_for_empty(self):
        name = _generate_name("", "project")
        self.assertEqual(name, "project note")


class TestLLMExtraction(unittest.TestCase):
    def test_parses_valid_json_response(self):
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(
            content=json.dumps([
                {"name": "User prefers vim", "description": "editor pref", "type": "user", "content": "Uses vim exclusively"},
                {"name": "Deploy on Friday", "description": "deadline", "type": "project", "content": "Release Friday"},
            ])
        )
        memories = asyncio.run(extract_memories_with_llm(
            [{"role": "user", "content": "I use vim and our release is Friday"}],
            provider,
        ))
        self.assertEqual(len(memories), 2)
        self.assertEqual(memories[0].name, "User prefers vim")

    def test_handles_json_in_code_block(self):
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(
            content='```json\n[{"name": "test", "description": "d", "type": "user", "content": "c"}]\n```'
        )
        memories = asyncio.run(extract_memories_with_llm(
            [{"role": "user", "content": "some message that is long enough"}],
            provider,
        ))
        self.assertEqual(len(memories), 1)

    def test_returns_empty_on_invalid_json(self):
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(content="Not valid JSON at all")
        memories = asyncio.run(extract_memories_with_llm(
            [{"role": "user", "content": "some long enough message here"}],
            provider,
        ))
        self.assertEqual(len(memories), 0)

    def test_filters_invalid_types(self):
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(
            content=json.dumps([{"name": "bad", "description": "d", "type": "invalid_type", "content": "c"}])
        )
        memories = asyncio.run(extract_memories_with_llm(
            [{"role": "user", "content": "enough content here to process"}],
            provider,
        ))
        self.assertEqual(len(memories), 0)

    def test_respects_max_cap(self):
        provider = AsyncMock()
        items = [{"name": f"mem{i}", "description": "d", "type": "user", "content": "c"} for i in range(20)]
        provider.send_message.return_value = MagicMock(content=json.dumps(items))
        memories = asyncio.run(extract_memories_with_llm(
            [{"role": "user", "content": "a message"}],
            provider,
        ))
        self.assertLessEqual(len(memories), _MAX_MEMORIES_PER_SESSION)

    def test_dedup_against_existing(self):
        provider = AsyncMock()
        provider.send_message.return_value = MagicMock(
            content=json.dumps([{"name": "Existing", "description": "d", "type": "user", "content": "c"}])
        )
        memories = asyncio.run(extract_memories_with_llm(
            [{"role": "user", "content": "enough text"}],
            provider,
            existing_names={"existing"},
        ))
        self.assertEqual(len(memories), 0)

    def test_empty_messages_returns_empty(self):
        provider = AsyncMock()
        memories = asyncio.run(extract_memories_with_llm([], provider))
        self.assertEqual(len(memories), 0)
        provider.send_message.assert_not_called()


if __name__ == "__main__":
    unittest.main()
