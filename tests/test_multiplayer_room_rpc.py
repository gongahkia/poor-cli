import logging
from types import SimpleNamespace

import pytest

from poor_cli.server.runtime import PoorCLIServer


class AuditSink:
    def __init__(self):
        self.events = []

    def log_event(self, **kwargs):
        self.events.append(kwargs)
        return "evt-test"


class FakeHost:
    def __init__(self):
        self.rooms = {"dev": object()}
        self.active_connection_id = "driver"
        self.members = {
            "driver": {"connectionId": "driver", "displayName": "Driver", "role": "prompter", "uiRole": "driver"},
            "viewer": {"connectionId": "viewer", "displayName": "Viewer", "role": "viewer", "uiRole": "navigator"},
        }

    def get_room_tokens(self):
        return {"dev": {"viewer": "viewer-token", "prompter": "prompter-token"}}

    def build_room_share_payload(self, room_name, role, *, signaling_url):
        return {"inviteCode": f"{role}-invite", "room": room_name, "signalingUrl": signaling_url}

    def list_room_members(self, room_name=None):
        if room_name and room_name != "dev":
            return []
        members = list(self.members.values())
        return [{
            "name": "dev",
            "mode": "mob",
            "memberCount": len(members),
            "members": members,
            "queueDepth": 0,
            "activeConnectionId": self.active_connection_id,
            "lobbyEnabled": False,
            "preset": "mob",
            "agendaSummary": {},
            "handsRaised": 0,
        }]

    def resolve_room_member_reference(self, room_name, reference):
        del room_name
        return reference if reference in self.members else None

    async def handoff_next_driver(self, room_name):
        assert room_name == "dev"
        self.active_connection_id = "viewer"
        self.members["driver"]["role"] = "viewer"
        self.members["driver"]["uiRole"] = "navigator"
        self.members["viewer"]["role"] = "prompter"
        self.members["viewer"]["uiRole"] = "driver"
        return "viewer"

    async def handoff_room_prompter(self, room_name, connection_id):
        assert room_name == "dev"
        if connection_id not in self.members:
            return False
        self.active_connection_id = connection_id
        for member_id, member in self.members.items():
            member["role"] = "prompter" if member_id == connection_id else "viewer"
            member["uiRole"] = "driver" if member_id == connection_id else "navigator"
        return True

    async def set_room_member_role(self, room_name, connection_id, role):
        assert room_name == "dev"
        if connection_id not in self.members:
            return False
        self.members[connection_id]["role"] = role
        return True

    def list_room_activity(self, room_name, limit, event_type=None):
        assert room_name == "dev"
        events = [
            {"eventType": "member_joined", "room": "dev", "actor": "driver"},
            {"eventType": "member_left", "room": "dev", "actor": "viewer"},
        ]
        if event_type:
            events = [event for event in events if event["eventType"] == event_type]
        return events[-limit:]


def make_server():
    server = PoorCLIServer.__new__(PoorCLIServer)
    server.initialized = True
    server.logger = logging.getLogger("test.multiplayer_room_rpc")
    server._embedded_multiplayer_room = False
    server._host_server_lock = None
    server._host_server = FakeHost()
    server._host_rooms = ["dev"]
    server._host_bind_host = "127.0.0.1"
    server._host_port = 8765
    server._host_local_signaling_url = "http://127.0.0.1:8765/rpc"
    server._host_share_signaling_url = "http://127.0.0.1:8765/rpc"
    server._host_public_signaling_url = None
    server._host_ngrok_enabled = False
    server.permission_mode = "prompt"
    server._maybe_core = lambda: SimpleNamespace(_audit_logger=None)
    return server


@pytest.mark.asyncio
async def test_collab_room_returns_invite_link_and_members():
    server = make_server()

    result = await server.handle_collab_room({"room": "dev"})

    assert result["room"]["name"] == "dev"
    assert result["room"]["inviteLink"] == "poor-cli --remote-invite prompter-invite"
    assert result["room"]["members"][0]["role"] == "prompter"
    assert result["room"]["members"][1]["role"] == "viewer"


@pytest.mark.asyncio
async def test_collab_room_pass_driver_updates_indicator_and_audits(monkeypatch):
    server = make_server()
    audit = AuditSink()
    monkeypatch.setattr("poor_cli.server.multiplayer_state.get_audit_logger", lambda: audit)

    result = await server.handle_collab_room_pass_driver({"room": "dev"})
    room = (await server.handle_collab_room({"room": "dev"}))["room"]

    assert result["connectionId"] == "viewer"
    assert room["activeConnectionId"] == "viewer"
    assert room["members"][1]["uiRole"] == "driver"
    assert audit.events[0]["operation"] == "multiplayer.driver.next"


@pytest.mark.asyncio
async def test_collab_room_events_returns_join_leave_events():
    server = make_server()

    result = await server.handle_collab_room_events({"room": "dev"})

    assert [event["eventType"] for event in result["events"]] == ["member_joined", "member_left"]
