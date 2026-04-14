import asyncio
import copy
from types import SimpleNamespace

from poor_cli.branch_tree import ConversationBranchStore
from poor_cli.server.handlers.branches import BranchesHandlersMixin
from poor_cli.server.handlers.chat_streaming import ChatStreamingHandlersMixin
from poor_cli.server.registry import REGISTRY


class Provider:
    def __init__(self, history):
        self.history = copy.deepcopy(history)
        self.restored = None

    def get_history(self):
        return copy.deepcopy(self.history)

    def set_history(self, messages):
        self.restored = copy.deepcopy(messages)
        self.history = copy.deepcopy(messages)


class Adapter:
    def __init__(self):
        self.linear = []
        self.branches = []
        self.active = None

    def add_message(self, role, content):
        self.linear.append((role, content))

    def add_branch_message(self, **kwargs):
        self.branches.append(kwargs)

    def set_active_leaf(self, turn_id):
        self.active = turn_id


class Server(BranchesHandlersMixin):
    def __init__(self, provider):
        async def send_message_sync(message, **kwargs):
            del kwargs
            if getattr(self.core, "history_adapter", None):
                self.core.history_adapter.add_message("user", message)
            provider.history.append({"role": "user", "content": message})
            provider.history.append({"role": "assistant", "content": "regen"})
            return "regen"

        self.core = SimpleNamespace(provider=provider, send_message_sync=send_message_sync)
        self._conversation_branches = ConversationBranchStore()

    def _ensure_initialized(self):
        return None


class EditServer(ChatStreamingHandlersMixin, BranchesHandlersMixin):
    def __init__(self, provider, adapter):
        self.core = SimpleNamespace(provider=provider, history_adapter=adapter)
        self._conversation_branches = ConversationBranchStore()


def test_branch_tree_renders_active_sibling():
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "one"}]
    store = ConversationBranchStore()
    store.sync_from_history(history)
    first = store.active_id
    sibling_snapshot = [history[0], {"role": "assistant", "content": "two"}]
    sibling = store.add_sibling(first, sibling_snapshot[-1], sibling_snapshot)

    payload = store.tree()
    root = payload["roots"][0]
    labels = [child["label"] for child in root["children"]]

    assert payload["activeId"] == sibling
    assert labels == ["assistant: one", "assistant: two"]
    assert root["children"][1]["active"] is True


def test_branch_switch_restores_provider_snapshot():
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "one"}]
    provider = Provider(history)
    server = Server(provider)

    tree = asyncio.run(REGISTRY["branches.tree"](server, {}))
    first = tree["activeId"]
    sibling_snapshot = [history[0], {"role": "assistant", "content": "two"}]
    sibling = server._branch_store().add_sibling(first, sibling_snapshot[-1], sibling_snapshot)

    result = asyncio.run(REGISTRY["branches.switch"](server, {"branchId": sibling}))

    assert result["activeId"] == sibling
    assert provider.restored == sibling_snapshot
    assert result["snapshot"] == sibling_snapshot


def test_regenerate_creates_sibling():
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "one"}]
    provider = Provider(history)
    server = Server(provider)

    tree = asyncio.run(REGISTRY["branches.tree"](server, {}))
    original = tree["activeId"]
    result = asyncio.run(REGISTRY["chat.regenerate"](server, {"turnId": original}))

    sibling = server._branch_store().nodes[result["newTurnId"]]
    original_node = server._branch_store().nodes[original]

    assert sibling.parent_id == original_node.parent_id
    assert sibling.branch_of == original
    assert result["activeId"] == sibling.node_id
    assert result["snapshot"][-1]["content"] == "regen"


def test_active_leaf_updates_after_regenerate_and_switch():
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "one"}]
    provider = Provider(history)
    server = Server(provider)

    tree = asyncio.run(REGISTRY["branches.tree"](server, {}))
    original = tree["activeId"]
    result = asyncio.run(REGISTRY["chat.regenerate"](server, {"turnId": original}))
    sibling = result["newTurnId"]
    switched = asyncio.run(REGISTRY["chat.switch"](server, {"branchId": sibling, "direction": "prev"}))

    assert result["activeLeaf"] == sibling
    assert switched["activeLeaf"] == original
    assert provider.restored == history


def test_regenerate_persists_sibling_without_linear_user_append():
    history = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "one"}]
    provider = Provider(history)
    server = Server(provider)
    adapter = Adapter()
    server.core.history_adapter = adapter

    tree = asyncio.run(REGISTRY["branches.tree"](server, {}))
    result = asyncio.run(REGISTRY["chat.regenerate"](server, {"turnId": tree["activeId"]}))

    assert adapter.linear == []
    assert adapter.branches == [{
        "role": "assistant",
        "content": "regen",
        "parent_id": "turn-1",
        "branch_of": "turn-2",
        "turn_id": result["newTurnId"],
    }]


def test_edit_resend_restores_parent_for_fork():
    history = [
        {"id": "turn-1", "role": "user", "content": "first", "parent_id": None},
        {"id": "turn-2", "role": "assistant", "content": "one", "parent_id": "turn-1"},
        {"id": "turn-3", "role": "user", "content": "original", "parent_id": "turn-2"},
        {"id": "turn-4", "role": "assistant", "content": "old", "parent_id": "turn-3"},
    ]
    provider = Provider(history)
    adapter = Adapter()
    server = EditServer(provider, adapter)

    server._restore_edit_parent({"editTurnId": "turn-3"})

    assert provider.restored == history[:2]
    assert server._branch_store().active_id == "turn-2"
    assert adapter.active == "turn-2"
