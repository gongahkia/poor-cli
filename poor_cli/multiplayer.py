"""Multiplayer WebSocket host runtime for poor-cli.

This module hosts room-scoped JSON-RPC sessions over WebSocket. Each room has
shared chat state, serialized prompt execution, role-based access control, and
room lifecycle notifications.
"""

from __future__ import annotations

import asyncio
from collections import deque
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from aiohttp import WSMsgType, web

from .exceptions import setup_logger

logger = setup_logger(__name__)


@dataclass
class InviteToken:
    """Room-scoped invite token."""

    token: str
    role: str  # viewer | prompter
    expires_at: Optional[str] = None


@dataclass
class ConnectionState:
    """Connected websocket client state."""

    connection_id: str
    ws: web.WebSocketResponse
    role: Optional[str] = None
    room_name: Optional[str] = None
    initialized: bool = False
    client_name: str = ""
    inline_server: Any = None
    joined_at: Optional[str] = None
    approved: bool = True
    hand_raised: bool = False
    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.monotonic)
    request_timestamps: Deque[float] = field(default_factory=deque)


@dataclass
class AgendaItem:
    """Room-scoped collaboration agenda item."""

    item_id: str
    text: str
    author: str
    created_at: str
    resolved: bool = False
    resolved_at: Optional[str] = None
    resolved_by: str = ""

    def to_payload(self) -> Dict[str, Any]:
        return {
            "id": self.item_id,
            "text": self.text,
            "author": self.author,
            "createdAt": self.created_at,
            "resolved": self.resolved,
            "resolvedAt": self.resolved_at or "",
            "resolvedBy": self.resolved_by,
        }


@dataclass
class QueuedRequest:
    """Queued request for room worker."""

    connection_id: str
    message: Any


@dataclass
class RoomState:
    """Per-room runtime state."""

    name: str
    server: Any
    tokens: Dict[str, InviteToken]
    members: Dict[str, ConnectionState] = field(default_factory=dict)
    request_queue: "asyncio.Queue[QueuedRequest]" = field(default_factory=asyncio.Queue)
    worker_task: Optional[asyncio.Task] = None
    dispatch_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    initialized: bool = False
    base_capabilities: Dict[str, Any] = field(default_factory=dict)
    active_connection_id: Optional[str] = None
    lobby_enabled: bool = False
    preset: str = "pairing"
    activity: List[Dict[str, Any]] = field(default_factory=list)
    agenda: List[AgendaItem] = field(default_factory=list)
    hand_raise_queue: List[str] = field(default_factory=list)
    next_agenda_id: int = 1


class MultiplayerHost:
    """WebSocket host for multiplayer poor-cli sessions."""

    _QUEUE_METHODS = {
        "chat",
        "poor-cli/chat",
        "poor-cli/chatStreaming",
    }

    _VIEWER_BLOCKED_METHODS = {
        "chat",
        "poor-cli/chat",
        "poor-cli/chatStreaming",
        "poor-cli/kickMember",
        "poor-cli/inlineComplete",
        "poor-cli/executeCommand",
        "poor-cli/applyEdit",
        "poor-cli/setConfig",
        "poor-cli/toggleConfig",
        "setConfig",
        "switchProvider",
        "poor-cli/switchProvider",
        "poor-cli/startHostServer",
        "poor-cli/getHostServerStatus",
        "poor-cli/stopHostServer",
        "poor-cli/setHostLobby",
        "poor-cli/approveHostMember",
        "poor-cli/denyHostMember",
        "poor-cli/rotateHostToken",
        "poor-cli/revokeHostToken",
        "poor-cli/handoffHostMember",
        "poor-cli/setHostPreset",
        "poor-cli/listHostActivity",
        "poor-cli/resolveAgendaItem",
        "poor-cli/nextDriver",
        "poor-cli/cancelRequest",
        "shutdown",
    }

    def __init__(
        self,
        *,
        bind_host: str,
        port: int,
        room_names: List[str],
        server_factory: Callable[[], Any],
        message_cls: Any,
        rpc_error_cls: Any,
        default_permission_mode: str = "prompt",
        heartbeat_interval_seconds: float = 30.0,
        pong_timeout_seconds: float = 60.0,
        requests_per_minute: int = 10,
    ):
        self.bind_host = bind_host
        self.port = port
        self.server_factory = server_factory
        self.message_cls = message_cls
        self.rpc_error_cls = rpc_error_cls
        self.default_permission_mode = default_permission_mode
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.pong_timeout_seconds = pong_timeout_seconds
        self.requests_per_minute = max(1, requests_per_minute)

        self.rooms: Dict[str, RoomState] = {}
        self.connections: Dict[str, ConnectionState] = {}
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._app: Optional[web.Application] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._stopped = False

        normalized_rooms = [name.strip() for name in room_names if name and name.strip()]
        if not normalized_rooms:
            normalized_rooms = ["default"]

        for room_name in normalized_rooms:
            self.rooms[room_name] = self._create_room(room_name)

    def _create_room(self, room_name: str) -> RoomState:
        server = self.server_factory()
        server.permission_mode = self.default_permission_mode
        server._embedded_multiplayer_room = True

        tokens = {
            "viewer": InviteToken(token=secrets.token_urlsafe(18), role="viewer"),
            "prompter": InviteToken(token=secrets.token_urlsafe(18), role="prompter"),
        }
        token_index = {token.token: token for token in tokens.values()}

        room = RoomState(name=room_name, server=server, tokens=token_index)

        async def _room_notification_sink(message: Any) -> None:
            method = str(getattr(message, "method", "") or "")
            params = getattr(message, "params", {}) or {}
            if not isinstance(params, dict):
                params = {}
            if method == "poor-cli/streamChunk":
                await self._broadcast_streaming_chunk(
                    room,
                    request_id=str(params.get("requestId", "")),
                    content=str(params.get("chunk", "")),
                    done=bool(params.get("done", False)),
                )
                return
            await self._broadcast_rpc(room, message)

        # Monkeypatch sink for streaming notifications from PoorCLIServer.
        room.server.write_message_stdio = _room_notification_sink  # type: ignore[attr-defined]
        room.worker_task = asyncio.create_task(
            self._room_worker(room), name=f"poor-cli-room-worker-{room_name}"
        )
        return room

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _room_mode(room: RoomState) -> str:
        if room.preset == "pairing":
            return "pair"
        return room.preset

    @staticmethod
    def _member_display_name(member: ConnectionState) -> str:
        return member.client_name or member.connection_id

    @staticmethod
    def _member_approval_state(member: ConnectionState) -> str:
        return "approved" if member.approved else "pending"

    def _member_ui_role(self, room: RoomState, member: ConnectionState) -> str:
        if member.role == "prompter" and member.approved:
            return "driver"
        if room.preset == "review":
            return "reviewer"
        return "navigator"

    @staticmethod
    def _ordered_member_items(room: RoomState) -> List[tuple[str, ConnectionState]]:
        return sorted(
            room.members.items(),
            key=lambda item: (item[1].connected_at, item[0]),
        )

    def _agenda_summary(self, room: RoomState) -> Dict[str, Any]:
        open_items = [item for item in room.agenda if not item.resolved]
        return {
            "total": len(room.agenda),
            "open": len(open_items),
            "openItems": [item.to_payload() for item in open_items[-10:]],
        }

    @staticmethod
    def _is_token_expired(invite: InviteToken) -> bool:
        if not invite.expires_at:
            return False
        try:
            expires_at = datetime.fromisoformat(invite.expires_at)
        except ValueError:
            return False
        now = datetime.now(expires_at.tzinfo or timezone.utc)
        return now >= expires_at

    def _room_member_snapshots(self, room: RoomState) -> List[Dict[str, Any]]:
        members: List[Dict[str, Any]] = []
        for connection_id, member in self._ordered_member_items(room):
            queue_position = 0
            if connection_id in room.hand_raise_queue:
                queue_position = room.hand_raise_queue.index(connection_id) + 1
            members.append(
                {
                    "connectionId": connection_id,
                    "role": member.role or "unknown",
                    "clientName": member.client_name,
                    "displayName": self._member_display_name(member),
                    "uiRole": self._member_ui_role(room, member),
                    "initialized": member.initialized,
                    "connected": not member.ws.closed,
                    "active": room.active_connection_id == connection_id,
                    "approved": member.approved,
                    "approvalState": self._member_approval_state(member),
                    "handRaised": member.hand_raised,
                    "queuePosition": queue_position,
                    "joinedAt": member.joined_at or "",
                }
            )
        return members

    def _list_room_member_payload(self, room: RoomState) -> List[Dict[str, Any]]:
        members: List[Dict[str, Any]] = []
        for connection_id, member in self._ordered_member_items(room):
            queue_position = 0
            if connection_id in room.hand_raise_queue:
                queue_position = room.hand_raise_queue.index(connection_id) + 1
            members.append(
                {
                    "connection_id": connection_id,
                    "role": member.role or "unknown",
                    "ui_role": self._member_ui_role(room, member),
                    "display_name": self._member_display_name(member),
                    "approval_state": self._member_approval_state(member),
                    "hand_raised": member.hand_raised,
                    "queue_position": queue_position,
                    "connected_at": member.connected_at,
                    "last_active": member.last_active,
                    "is_active_prompter": member.role == "prompter",
                }
            )
        return members

    def _pick_room_prompter(
        self,
        room: RoomState,
        *,
        preferred_connection_id: Optional[str] = None,
        promote_fallback: bool = False,
    ) -> Optional[str]:
        approved_member_ids = [
            connection_id
            for connection_id, member in room.members.items()
            if member.approved and not member.ws.closed
        ]
        if not approved_member_ids:
            return None

        if preferred_connection_id:
            preferred = room.members.get(preferred_connection_id)
            if preferred is not None and preferred.approved and not preferred.ws.closed:
                return preferred_connection_id

        approved_prompters = [
            connection_id
            for connection_id in approved_member_ids
            if room.members[connection_id].role == "prompter"
        ]
        if approved_prompters:
            if room.active_connection_id in approved_prompters:
                return room.active_connection_id
            return approved_prompters[0]

        if promote_fallback:
            return approved_member_ids[0]
        return None

    def _rebalance_room_roles(
        self,
        room: RoomState,
        *,
        preferred_connection_id: Optional[str] = None,
        promote_fallback: bool = False,
    ) -> Optional[str]:
        promoted_connection_id = self._pick_room_prompter(
            room,
            preferred_connection_id=preferred_connection_id,
            promote_fallback=promote_fallback,
        )
        if promoted_connection_id is None:
            return None

        for connection_id, member in room.members.items():
            if not member.approved or member.ws.closed:
                continue
            member.role = "prompter" if connection_id == promoted_connection_id else "viewer"
        return promoted_connection_id

    async def _broadcast_member_role_updates(self, room: RoomState) -> None:
        for connection_id, member in room.members.items():
            notification = self.message_cls(
                method="poor-cli/memberRoleUpdated",
                params={
                    "room": room.name,
                    "connectionId": connection_id,
                    "role": member.role or "viewer",
                    "uiRole": self._member_ui_role(room, member),
                },
            )
            await self._broadcast_rpc(room, notification)

    def _record_activity(
        self,
        room: RoomState,
        *,
        event_type: str,
        actor: str = "",
        request_id: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        event = {
            "timestamp": self._now_iso(),
            "eventType": event_type,
            "room": room.name,
            "actor": actor,
            "requestId": request_id,
            "details": details or {},
        }
        room.activity.append(event)
        if len(room.activity) > 300:
            del room.activity[:-300]

    @staticmethod
    def _prune_hand_raise_queue(room: RoomState) -> None:
        room.hand_raise_queue = [
            connection_id
            for connection_id in room.hand_raise_queue
            if (
                connection_id in room.members
                and room.members[connection_id].approved
                and not room.members[connection_id].ws.closed
                and room.members[connection_id].role != "prompter"
            )
        ]

    def resolve_room_member_reference(self, room_name: str, reference: str) -> Optional[str]:
        room = self.rooms.get(room_name)
        if room is None:
            return None
        normalized = str(reference or "").strip()
        if not normalized:
            return None

        member = room.members.get(normalized)
        if member is not None and not member.ws.closed:
            return normalized

        if normalized.startswith("@"):
            normalized = normalized[1:].strip()

        ordered_members = self._ordered_member_items(room)
        if normalized.startswith("#") and normalized[1:].isdigit():
            index = int(normalized[1:]) - 1
            if 0 <= index < len(ordered_members):
                return ordered_members[index][0]

        if normalized.isdigit():
            index = int(normalized) - 1
            if 0 <= index < len(ordered_members):
                return ordered_members[index][0]

        lowered = normalized.lower()
        for connection_id, member_state in ordered_members:
            display_name = self._member_display_name(member_state).lower()
            if display_name == lowered or connection_id.lower() == lowered:
                return connection_id
        return None

    def list_room_agenda(
        self,
        room_name: str,
        *,
        include_resolved: bool = True,
    ) -> List[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return []
        items = room.agenda
        if not include_resolved:
            items = [item for item in items if not item.resolved]
        return [item.to_payload() for item in items]

    async def add_room_agenda_item(
        self,
        room_name: str,
        text: str,
        *,
        author: str,
        actor_connection_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return None

        normalized_text = str(text or "").strip()
        if not normalized_text:
            raise ValueError("agenda text cannot be empty")

        item = AgendaItem(
            item_id=f"a-{room.next_agenda_id}",
            text=normalized_text,
            author=author.strip() or "unknown",
            created_at=self._now_iso(),
        )
        room.next_agenda_id += 1
        room.agenda.append(item)
        await self._broadcast_room_event(
            room,
            "agenda_added",
            actor=actor_connection_id,
            queue_depth=room.request_queue.qsize(),
            details={"agendaItem": item.to_payload()},
        )
        return item.to_payload()

    async def resolve_room_agenda_item(
        self,
        room_name: str,
        item_id: str,
        *,
        resolved_by: str,
        actor_connection_id: str = "",
    ) -> Optional[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return None

        normalized_id = str(item_id or "").strip()
        if not normalized_id:
            raise ValueError("agenda item id is required")

        for item in room.agenda:
            if item.item_id != normalized_id:
                continue
            item.resolved = True
            item.resolved_at = self._now_iso()
            item.resolved_by = resolved_by.strip() or "unknown"
            await self._broadcast_room_event(
                room,
                "agenda_resolved",
                actor=actor_connection_id,
                queue_depth=room.request_queue.qsize(),
                details={"agendaItem": item.to_payload()},
            )
            return item.to_payload()
        return None

    async def set_room_member_hand_raised(
        self,
        room_name: str,
        connection_id: str,
        raised: bool,
    ) -> Optional[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return None

        member = room.members.get(connection_id)
        if member is None or member.ws.closed or not member.approved:
            return None

        if member.role == "prompter":
            member.hand_raised = False
            self._prune_hand_raise_queue(room)
            return {
                "connectionId": connection_id,
                "handRaised": False,
                "queuePosition": 0,
            }

        member.hand_raised = bool(raised)
        self._prune_hand_raise_queue(room)
        if member.hand_raised:
            if connection_id not in room.hand_raise_queue:
                room.hand_raise_queue.append(connection_id)
        else:
            room.hand_raise_queue = [
                queued_id for queued_id in room.hand_raise_queue if queued_id != connection_id
            ]
        queue_position = 0
        if connection_id in room.hand_raise_queue:
            queue_position = room.hand_raise_queue.index(connection_id) + 1
        await self._broadcast_room_event(
            room,
            "hand_raised" if member.hand_raised else "hand_lowered",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
            details={
                "connectionId": connection_id,
                "handRaised": member.hand_raised,
                "queuePosition": queue_position,
            },
        )
        return {
            "connectionId": connection_id,
            "handRaised": member.hand_raised,
            "queuePosition": queue_position,
        }

    async def handoff_next_driver(
        self,
        room_name: str,
        *,
        actor_connection_id: str = "",
    ) -> Optional[str]:
        room = self.rooms.get(room_name)
        if room is None:
            return None

        self._prune_hand_raise_queue(room)
        next_connection_id = next(
            (connection_id for connection_id in room.hand_raise_queue if connection_id != actor_connection_id),
            None,
        )
        if next_connection_id is None:
            ordered_members = [
                connection_id
                for connection_id, member in self._ordered_member_items(room)
                if member.approved and not member.ws.closed
            ]
            if not ordered_members:
                return None
            if actor_connection_id in ordered_members:
                start_index = ordered_members.index(actor_connection_id) + 1
                rotated = ordered_members[start_index:] + ordered_members[:start_index]
            else:
                rotated = ordered_members
            next_connection_id = next(
                (connection_id for connection_id in rotated if connection_id != actor_connection_id),
                None,
            )
        if next_connection_id is None:
            return None
        updated = await self.handoff_room_prompter(room_name, next_connection_id)
        if not updated:
            return None
        room.hand_raise_queue = [
            connection_id for connection_id in room.hand_raise_queue if connection_id != next_connection_id
        ]
        target = room.members.get(next_connection_id)
        if target is not None:
            target.hand_raised = False
        await self._broadcast_room_event(
            room,
            "next_driver_selected",
            actor=next_connection_id,
            queue_depth=room.request_queue.qsize(),
            details={"connectionId": next_connection_id},
        )
        return next_connection_id

    def get_room_tokens(self) -> Dict[str, Dict[str, str]]:
        """Return room->role->token mapping for host-local sharing."""
        output: Dict[str, Dict[str, str]] = {}
        for room_name, room in self.rooms.items():
            role_map: Dict[str, str] = {}
            expired_tokens: List[str] = []
            for token_value, invite in room.tokens.items():
                if self._is_token_expired(invite):
                    expired_tokens.append(token_value)
                    continue
                role_map[invite.role] = invite.token
            for token_value in expired_tokens:
                room.tokens.pop(token_value, None)
            output[room_name] = role_map
        return output

    def list_room_members(self, room_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Return structured room/member snapshots for host-side admin tooling."""
        selected_rooms: List[str]
        if room_name:
            selected_rooms = [room_name] if room_name in self.rooms else []
        else:
            selected_rooms = sorted(self.rooms.keys())

        output: List[Dict[str, Any]] = []
        for selected_room in selected_rooms:
            room = self.rooms.get(selected_room)
            if room is None:
                continue

            members = self._room_member_snapshots(room)
            output.append(
                {
                    "name": selected_room,
                    "mode": self._room_mode(room),
                    "memberCount": len(members),
                    "members": members,
                    "queueDepth": room.request_queue.qsize(),
                    "activeConnectionId": room.active_connection_id or "",
                    "lobbyEnabled": room.lobby_enabled,
                    "preset": room.preset,
                    "agendaSummary": self._agenda_summary(room),
                    "handsRaised": len(room.hand_raise_queue),
                }
            )
        return output

    def list_room_activity(
        self,
        room_name: str,
        limit: int = 50,
        event_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return []
        bounded = max(1, min(limit, 200))
        items = room.activity
        if event_type:
            normalized = event_type.strip().lower()
            items = [
                item
                for item in room.activity
                if str(item.get("eventType", "")).strip().lower() == normalized
            ]
        return [dict(item) for item in items[-bounded:]]

    async def set_room_lobby(self, room_name: str, enabled: bool) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False
        room.lobby_enabled = enabled
        roles_rebalanced = False
        if not enabled:
            for member in room.members.values():
                member.approved = True
            self._rebalance_room_roles(room)
            roles_rebalanced = True
        self._prune_hand_raise_queue(room)
        if roles_rebalanced:
            await self._broadcast_member_role_updates(room)
        await self._broadcast_room_event(
            room,
            "lobby_updated",
            details={"lobbyEnabled": enabled},
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def approve_room_member(self, room_name: str, connection_id: str) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False

        member = room.members.get(connection_id)
        if member is None:
            return False

        member.approved = True
        promoted_connection_id = None
        if member.role == "prompter":
            promoted_connection_id = self._rebalance_room_roles(
                room,
                preferred_connection_id=connection_id,
            )
        self._prune_hand_raise_queue(room)
        if promoted_connection_id is not None:
            await self._broadcast_member_role_updates(room)
        await self._broadcast_room_event(
            room,
            "member_approved",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def deny_room_member(self, room_name: str, connection_id: str) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False

        member = room.members.pop(connection_id, None)
        if member is None:
            return False

        self.connections.pop(connection_id, None)
        if room.active_connection_id == connection_id:
            room.active_connection_id = None
        room.hand_raise_queue = [
            queued_id for queued_id in room.hand_raise_queue if queued_id != connection_id
        ]
        promoted_connection_id = None
        if member.role == "prompter":
            promoted_connection_id = self._rebalance_room_roles(room, promote_fallback=True)

        try:
            await member.ws.close(code=4003, message=b"Denied by host")
        except Exception:
            pass

        if promoted_connection_id is not None:
            await self._broadcast_member_role_updates(room)

        await self._broadcast_room_event(
            room,
            "member_denied",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def rotate_room_token(
        self,
        room_name: str,
        role: str,
        *,
        expires_in_seconds: Optional[int] = None,
    ) -> Optional[str]:
        room = self.rooms.get(room_name)
        if room is None:
            return None

        normalized_role = role.strip().lower()
        if normalized_role not in {"viewer", "prompter"}:
            raise ValueError("role must be viewer or prompter")

        stale_tokens = [
            token_value
            for token_value, invite in room.tokens.items()
            if invite.role == normalized_role
        ]
        for token_value in stale_tokens:
            room.tokens.pop(token_value, None)

        expires_at: Optional[str] = None
        if expires_in_seconds is not None and expires_in_seconds > 0:
            expires_at = (
                datetime.now(timezone.utc) + timedelta(seconds=expires_in_seconds)
            ).isoformat()

        new_token = secrets.token_urlsafe(18)
        room.tokens[new_token] = InviteToken(
            token=new_token,
            role=normalized_role,
            expires_at=expires_at,
        )
        await self._broadcast_room_event(
            room,
            "token_rotated",
            details={"role": normalized_role},
            queue_depth=room.request_queue.qsize(),
        )
        return new_token

    async def revoke_room_token(self, room_name: str, token: str) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False

        invite = room.tokens.pop(token, None)
        if invite is None:
            return False

        await self._broadcast_room_event(
            room,
            "token_revoked",
            details={"role": invite.role},
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def handoff_room_prompter(self, room_name: str, connection_id: str) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False

        target = room.members.get(connection_id)
        if target is None:
            return False
        if target.ws.closed or not target.approved:
            return False

        target.hand_raised = False
        room.hand_raise_queue = [
            queued_id for queued_id in room.hand_raise_queue if queued_id != connection_id
        ]
        self._rebalance_room_roles(room, preferred_connection_id=connection_id)
        await self._broadcast_member_role_updates(room)

        await self._broadcast_room_event(
            room,
            "role_handoff",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def set_room_preset(self, room_name: str, preset: str) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False

        normalized = preset.strip().lower()
        if normalized not in {"pairing", "mob", "review"}:
            raise ValueError("preset must be one of: pairing, mob, review")

        room.preset = normalized
        if normalized == "pairing":
            room.lobby_enabled = False
            room.hand_raise_queue.clear()
            for member in room.members.values():
                member.hand_raised = False
        else:
            room.lobby_enabled = True
        self._prune_hand_raise_queue(room)

        await self._broadcast_room_event(
            room,
            "preset_updated",
            details={
                "preset": normalized,
                "mode": self._room_mode(room),
                "lobbyEnabled": room.lobby_enabled,
            },
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def remove_room_member(self, room_name: str, connection_id: str) -> bool:
        """Disconnect/remove a room member by connection id."""
        room = self.rooms.get(room_name)
        if room is None:
            return False

        member = room.members.pop(connection_id, None)
        if member is None:
            return False

        self.connections.pop(connection_id, None)
        if room.active_connection_id == connection_id:
            room.active_connection_id = None
        room.hand_raise_queue = [
            queued_id for queued_id in room.hand_raise_queue if queued_id != connection_id
        ]
        promoted_connection_id = None
        if member.role == "prompter":
            promoted_connection_id = self._rebalance_room_roles(room, promote_fallback=True)

        try:
            await member.ws.close(code=4001, message=b"Removed by host")
        except Exception:
            pass

        if promoted_connection_id is not None:
            await self._broadcast_member_role_updates(room)

        await self._broadcast_room_event(
            room,
            "member_removed",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def set_room_member_role(self, room_name: str, connection_id: str, role: str) -> bool:
        """Update a connected member role (viewer/prompter)."""
        room = self.rooms.get(room_name)
        if room is None:
            return False

        member = room.members.get(connection_id)
        if member is None:
            return False

        normalized_role = role.strip().lower()
        if normalized_role not in {"viewer", "prompter"}:
            raise ValueError("role must be viewer or prompter")

        member.role = normalized_role
        if normalized_role == "prompter":
            member.hand_raised = False
            self._rebalance_room_roles(room, preferred_connection_id=connection_id)
        else:
            fallback_connection_id = next(
                (
                    other_connection_id
                    for other_connection_id, other_member in room.members.items()
                    if other_connection_id != connection_id
                    and other_member.approved
                    and not other_member.ws.closed
                ),
                None,
            )
            self._rebalance_room_roles(
                room,
                preferred_connection_id=fallback_connection_id,
                promote_fallback=fallback_connection_id is None,
            )
        self._prune_hand_raise_queue(room)
        await self._broadcast_member_role_updates(room)
        await self._broadcast_room_event(
            room,
            "member_role_updated",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def start(self) -> None:
        """Start the HTTP/WebSocket host."""
        app = web.Application()
        app.router.add_get("/rpc", self._handle_ws)
        app.router.add_get("/health", self._handle_health)

        self._app = app
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.bind_host, port=self.port)
        await self._site.start()
        self._heartbeat_task = asyncio.create_task(
            self._heartbeat_loop(), name="poor-cli-multiplayer-heartbeat"
        )
        logger.info("Multiplayer host listening on ws://%s:%s/rpc", self.bind_host, self.port)

    async def stop(self) -> None:
        """Stop host and workers."""
        if self._stopped:
            return
        self._stopped = True

        for room in self.rooms.values():
            if room.worker_task:
                room.worker_task.cancel()
        if self._heartbeat_task:
            self._heartbeat_task.cancel()

        for room in self.rooms.values():
            if room.worker_task:
                try:
                    await room.worker_task
                except asyncio.CancelledError:
                    pass
        if self._heartbeat_task:
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        for conn in list(self.connections.values()):
            try:
                await conn.ws.close()
            except Exception:
                pass

        if self._runner:
            await self._runner.cleanup()

    async def run_forever(self) -> None:
        """Run host until interrupted."""
        await self.start()
        try:
            while True:
                await asyncio.sleep(3600)
        finally:
            await self.stop()

    async def _handle_health(self, request: web.Request) -> web.Response:
        del request
        return web.json_response(
            {
                "ok": True,
                "rooms": sorted(self.rooms.keys()),
                "connections": len(self.connections),
            }
        )

    async def _handle_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        conn = ConnectionState(connection_id=uuid.uuid4().hex[:12], ws=ws)
        self.connections[conn.connection_id] = conn

        try:
            async for incoming in ws:
                if incoming.type == WSMsgType.PONG:
                    conn.last_pong = time.monotonic()
                    conn.last_active = time.time()
                    continue
                if incoming.type != WSMsgType.TEXT:
                    if incoming.type in {WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED}:
                        break
                    continue

                try:
                    payload = json.loads(incoming.data)
                except json.JSONDecodeError:
                    await self._send_error_response(
                        ws,
                        request_id=None,
                        code=self.rpc_error_cls.PARSE_ERROR,
                        message="Invalid JSON",
                        data={"error_code": "PARSE_ERROR"},
                    )
                    continue

                if not isinstance(payload, dict):
                    await self._send_error_response(
                        ws,
                        request_id=None,
                        code=self.rpc_error_cls.INVALID_REQUEST,
                        message="JSON-RPC payload must be an object",
                        data={"error_code": "INVALID_REQUEST"},
                    )
                    continue

                message = self.message_cls.from_dict(payload)
                await self._handle_message(conn, message)

        finally:
            await self._cleanup_connection(conn)

        return ws

    async def _handle_message(self, conn: ConnectionState, message: Any) -> None:
        conn.last_pong = time.monotonic()
        conn.last_active = time.time()

        if not conn.initialized:
            if message.method != "initialize":
                await self._send_error_response(
                    conn.ws,
                    request_id=message.id,
                    code=self.rpc_error_cls.INVALID_REQUEST,
                    message="Connection not initialized. Call initialize with room and inviteToken.",
                    data={"error_code": "NOT_INITIALIZED"},
                )
                return

            await self._handle_initialize(conn, message)
            return

        if conn.room_name is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Initialized connection has no room",
                data={"error_code": "ROOM_MISSING"},
            )
            return

        room = self.rooms.get(conn.room_name)
        if room is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_REQUEST,
                message=f"Unknown room: {conn.room_name}",
                data={"error_code": "ROOM_NOT_FOUND"},
            )
            return

        method = message.method or ""

        if method in {"poor-cli/permissionRes", "poor-cli/planRes"}:
            if conn.role != "prompter" or not conn.approved:
                await self._send_error_response(
                    conn.ws,
                    request_id=message.id,
                    code=self.rpc_error_cls.INTERNAL_ERROR,
                    message="Only the active driver can answer interactive review prompts",
                    data={"error_code": "permission_denied", "role": conn.role},
                )
                return
            await room.server._handle_notification(message)
            return

        if not conn.approved:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Connection is pending host approval",
                data={"error_code": "PENDING_APPROVAL", "role": conn.role},
            )
            return

        if method == "poor-cli/suggestText":
            await self._handle_suggest_text(conn, room, message)
            return

        if method == "poor-cli/addAgendaItem":
            await self._handle_add_agenda_item(conn, room, message)
            return

        if method == "poor-cli/listAgenda":
            await self._handle_list_agenda(conn, room, message)
            return

        if method == "poor-cli/resolveAgendaItem":
            await self._handle_resolve_agenda_item(conn, room, message)
            return

        if method == "poor-cli/setHandRaised":
            await self._handle_set_hand_raised(conn, room, message)
            return

        if method == "poor-cli/nextDriver":
            await self._handle_next_driver(conn, room, message)
            return

        if method == "poor-cli/passDriver":
            await self._handle_pass_driver(conn, room, message)
            return

        if conn.role == "viewer" and method in self._VIEWER_BLOCKED_METHODS:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message=f"Method not allowed for viewer role: {method}",
                data={"error_code": "permission_denied", "role": conn.role, "method": method},
            )
            return

        if method == "poor-cli/cancelRequest" and room.active_connection_id not in {
            None,
            conn.connection_id,
        }:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Only active requester can cancel the in-flight request",
                data={
                    "error_code": "permission_denied",
                    "role": conn.role,
                    "method": method,
                },
            )
            return

        if method == "poor-cli/inlineComplete":
            response = await self._dispatch_inline_isolated(conn, room, message)
            if message.id is not None:
                await self._send_rpc(conn.ws, response)
            return

        if method == "poor-cli/kickMember":
            await self._handle_kick_member(conn, room, message)
            return

        if method == "poor-cli/listRoomMembers":
            params = message.params or {}
            room_name = str(params.get("room", room.name)).strip() or room.name
            if room_name != room.name:
                await self._send_error_response(
                    conn.ws,
                    request_id=message.id,
                    code=self.rpc_error_cls.INVALID_PARAMS,
                    message=f"Unknown room: {room_name}",
                    data={"error_code": "ROOM_NOT_FOUND"},
                )
                return

            if message.id is not None:
                await self._send_rpc(
                    conn.ws,
                    self.message_cls(
                        id=message.id,
                        result={
                            "room": room.name,
                            "members": self._list_room_member_payload(room),
                            "mode": self._room_mode(room),
                            "agendaSummary": self._agenda_summary(room),
                        },
                    ),
                )
            return

        if method in self._QUEUE_METHODS:
            if not self._consume_rate_limit_token(conn):
                await self._send_error_response(
                    conn.ws,
                    request_id=message.id,
                    code=-32029,
                    message="Rate limited",
                    data={
                        "error_code": "RATE_LIMITED",
                        "requestsPerMinute": self.requests_per_minute,
                    },
                )
                return
            await room.request_queue.put(QueuedRequest(connection_id=conn.connection_id, message=message))
            await self._broadcast_room_event(
                room,
                "queued",
                request_id=self._extract_request_id(message),
                actor=conn.connection_id,
                queue_depth=room.request_queue.qsize(),
            )
            return

        async with room.dispatch_lock:
            response = await room.server.dispatch(message)
        if message.id is not None:
            await self._send_rpc(conn.ws, response)

    def _consume_rate_limit_token(self, conn: ConnectionState) -> bool:
        now = time.monotonic()
        window_start = now - 60.0
        timestamps = conn.request_timestamps
        while timestamps and timestamps[0] < window_start:
            timestamps.popleft()

        if len(timestamps) >= self.requests_per_minute:
            return False

        timestamps.append(now)
        return True

    async def _handle_add_agenda_item(self, conn: ConnectionState, room: RoomState, message: Any) -> None:
        params = message.params or {}
        text = str(params.get("text", "")).strip()
        if not text:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="text is required",
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        try:
            item = await self.add_room_agenda_item(
                room.name,
                text,
                author=self._member_display_name(conn),
                actor_connection_id=conn.connection_id,
            )
        except ValueError as error:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=str(error),
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={
                        "success": True,
                        "room": room.name,
                        "item": item,
                        "agendaSummary": self._agenda_summary(room),
                    },
                ),
            )

    async def _handle_list_agenda(self, conn: ConnectionState, room: RoomState, message: Any) -> None:
        params = message.params or {}
        include_resolved = bool(params.get("includeResolved", True))
        if message.id is None:
            return
        await self._send_rpc(
            conn.ws,
            self.message_cls(
                id=message.id,
                result={
                    "room": room.name,
                    "items": self.list_room_agenda(room.name, include_resolved=include_resolved),
                    "agendaSummary": self._agenda_summary(room),
                },
            ),
        )

    async def _handle_resolve_agenda_item(
        self,
        conn: ConnectionState,
        room: RoomState,
        message: Any,
    ) -> None:
        if conn.role != "prompter" or not conn.approved:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Only the active driver can resolve agenda items",
                data={"error_code": "permission_denied", "role": conn.role},
            )
            return

        params = message.params or {}
        item_id = str(params.get("itemId", params.get("id", ""))).strip()
        if not item_id:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="itemId is required",
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        try:
            item = await self.resolve_room_agenda_item(
                room.name,
                item_id,
                resolved_by=self._member_display_name(conn),
                actor_connection_id=conn.connection_id,
            )
        except ValueError as error:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=str(error),
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        if item is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=f"Unknown agenda item: {item_id}",
                data={"error_code": "AGENDA_NOT_FOUND"},
            )
            return

        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={
                        "success": True,
                        "room": room.name,
                        "item": item,
                        "agendaSummary": self._agenda_summary(room),
                    },
                ),
            )

    async def _handle_set_hand_raised(
        self,
        conn: ConnectionState,
        room: RoomState,
        message: Any,
    ) -> None:
        params = message.params or {}
        raised = bool(params.get("raised", True))
        result = await self.set_room_member_hand_raised(room.name, conn.connection_id, raised)
        if result is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="Unable to update hand raise state",
                data={"error_code": "INVALID_PARAMS"},
            )
            return
        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={
                        "success": True,
                        "room": room.name,
                        **result,
                    },
                ),
            )

    async def _handle_next_driver(self, conn: ConnectionState, room: RoomState, message: Any) -> None:
        if conn.role != "prompter" or not conn.approved:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Only the active driver can hand off to the next driver",
                data={"error_code": "permission_denied", "role": conn.role},
            )
            return

        connection_id = await self.handoff_next_driver(
            room.name,
            actor_connection_id=conn.connection_id,
        )
        if connection_id is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="No eligible member found to receive driver role",
                data={"error_code": "MEMBER_NOT_FOUND"},
            )
            return

        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={
                        "success": True,
                        "room": room.name,
                        "connectionId": connection_id,
                    },
                ),
            )

    async def _handle_kick_member(self, conn: ConnectionState, room: RoomState, message: Any) -> None:
        params = message.params or {}
        target_connection_id = str(
            params.get("connectionId", params.get("connection_id", ""))
        ).strip()
        target_room = str(params.get("room", room.name)).strip() or room.name

        if conn.role not in {"prompter", "host", "admin"}:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Only host/admin can kick room members",
                data={"error_code": "permission_denied", "role": conn.role},
            )
            return

        if target_room != room.name:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=f"Unknown room: {target_room}",
                data={"error_code": "ROOM_NOT_FOUND"},
            )
            return

        if not target_connection_id:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="connectionId is required",
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        resolved_connection_id = self.resolve_room_member_reference(room.name, target_connection_id)
        if resolved_connection_id:
            target_connection_id = resolved_connection_id

        if target_connection_id == conn.connection_id:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="Cannot kick your own connection",
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        member = room.members.pop(target_connection_id, None)
        if member is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=f"Unknown connection id: {target_connection_id}",
                data={"error_code": "MEMBER_NOT_FOUND"},
            )
            return

        self.connections.pop(target_connection_id, None)
        if room.active_connection_id == target_connection_id:
            room.active_connection_id = None
        room.hand_raise_queue = [
            queued_id for queued_id in room.hand_raise_queue if queued_id != target_connection_id
        ]
        promoted_connection_id = None
        if member.role == "prompter":
            promoted_connection_id = self._rebalance_room_roles(room, promote_fallback=True)

        try:
            await member.ws.close(code=4001, message=b"Kicked by host")
        except Exception:
            pass

        if promoted_connection_id is not None:
            await self._broadcast_member_role_updates(room)

        await self._broadcast_room_event(
            room,
            "member_kicked",
            actor=conn.connection_id,
            queue_depth=room.request_queue.qsize(),
            details={"targetConnectionId": target_connection_id},
        )

        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={
                        "ok": True,
                        "room": room.name,
                        "connectionId": target_connection_id,
                        "kickedBy": conn.connection_id,
                    },
                ),
            )

    async def _dispatch_inline_isolated(self, conn: ConnectionState, room: RoomState, message: Any) -> Any:
        if conn.inline_server is None:
            conn.inline_server = self.server_factory()
            provider_info = {}
            room_core = getattr(room.server, "core", None)
            if room_core is not None and getattr(room.server, "initialized", False):
                provider_info = room.server.core.get_provider_info()
            init_params: Dict[str, Any] = {
                "provider": provider_info.get("name"),
                "model": provider_info.get("model"),
            }
            init_params = {k: v for k, v in init_params.items() if v}
            await conn.inline_server.handle_initialize(init_params)

            # Disable persistence for isolated inline engine.
            inline_core = getattr(conn.inline_server, "core", None)
            if inline_core is not None:
                inline_core.history_adapter = None

        response = await conn.inline_server.dispatch(message)
        return response

    async def _handle_pass_driver(self, conn: ConnectionState, room: RoomState, message: Any) -> None:
        params = message.params or {}
        requested_room = str(params.get("room", room.name)).strip() or room.name
        if requested_room != room.name:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=f"Unknown room: {requested_room}",
                data={"error_code": "ROOM_NOT_FOUND"},
            )
            return

        if conn.role != "prompter" or not conn.approved:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INTERNAL_ERROR,
                message="Only the active driver can pass driver role",
                data={"error_code": "permission_denied", "role": conn.role},
            )
            return

        display_name = str(params.get("displayName", "")).strip()
        target_connection_id = str(params.get("connectionId", "")).strip()
        target: Optional[ConnectionState] = None

        if target_connection_id:
            resolved_connection_id = self.resolve_room_member_reference(room.name, target_connection_id)
            if resolved_connection_id:
                target_connection_id = resolved_connection_id
            target = room.members.get(target_connection_id)
        elif display_name:
            resolved_connection_id = self.resolve_room_member_reference(room.name, display_name)
            if resolved_connection_id:
                target = room.members.get(resolved_connection_id)
        else:
            if room.preset == "mob":
                next_connection_id = await self.handoff_next_driver(
                    room.name,
                    actor_connection_id=conn.connection_id,
                )
                if next_connection_id is None:
                    await self._send_error_response(
                        conn.ws,
                        request_id=message.id,
                        code=self.rpc_error_cls.INVALID_PARAMS,
                        message="No eligible member found to receive driver role",
                        data={"error_code": "MEMBER_NOT_FOUND"},
                    )
                    return
                if message.id is not None:
                    await self._send_rpc(
                        conn.ws,
                        self.message_cls(
                            id=message.id,
                            result={
                                "success": True,
                                "room": room.name,
                                "connectionId": next_connection_id,
                            },
                        ),
                    )
                return
            for _, member in self._ordered_member_items(room):
                if member.connection_id == conn.connection_id:
                    continue
                if member.ws.closed or not member.approved:
                    continue
                target = member
                break

        if target is None:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="No eligible member found to receive driver role",
                data={"error_code": "MEMBER_NOT_FOUND"},
            )
            return

        if target.connection_id == conn.connection_id:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="Driver role is already assigned to this connection",
                data={"error_code": "INVALID_PARAMS"},
            )
            return

        if target.ws.closed or not target.approved:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="Cannot pass driver role to a pending or disconnected member",
                data={"error_code": "MEMBER_NOT_ELIGIBLE"},
            )
            return

        updated = await self.handoff_room_prompter(room.name, target.connection_id)
        if not updated:
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message=f"Could not hand off driver role to `{target.connection_id}`",
                data={"error_code": "MEMBER_NOT_FOUND"},
            )
            return

        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={
                        "success": True,
                        "room": room.name,
                        "connectionId": target.connection_id,
                    },
                ),
            )

    async def _handle_initialize(self, conn: ConnectionState, message: Any) -> None:
        params = message.params or {}
        room_name = str(params.get("room", "")).strip()
        invite_token = str(params.get("inviteToken", "")).strip()
        client_name = str(params.get("clientName", "")).strip()

        room = self.rooms.get(room_name)
        invite = room.tokens.get(invite_token) if room else None

        if room is None or invite is None or self._is_token_expired(invite):
            if room is not None and invite is not None and self._is_token_expired(invite):
                room.tokens.pop(invite_token, None)
            await self._send_error_response(
                conn.ws,
                request_id=message.id,
                code=self.rpc_error_cls.INVALID_PARAMS,
                message="Invalid room or inviteToken",
                data={"error_code": "INVALID_MULTIPLAYER_AUTH"},
            )
            return

        conn.role = invite.role
        conn.room_name = room_name
        conn.client_name = client_name
        conn.joined_at = datetime.now().isoformat()
        conn.approved = not room.lobby_enabled
        conn.hand_raised = False

        if not room.initialized:
            init_params = dict(params)
            init_params.pop("room", None)
            init_params.pop("inviteToken", None)
            init_params.pop("clientName", None)
            result = await room.server.handle_initialize(init_params)
            room.initialized = True
            room.base_capabilities = dict(result.get("capabilities", {}))

        conn.initialized = True
        room.members[conn.connection_id] = conn
        if conn.approved and conn.role == "prompter":
            self._rebalance_room_roles(room, preferred_connection_id=conn.connection_id)
        self._prune_hand_raise_queue(room)

        capabilities = dict(room.base_capabilities)
        capabilities["multiplayer"] = {
            "enabled": True,
            "room": room_name,
            "mode": self._room_mode(room),
            "role": conn.role,
            "uiRole": self._member_ui_role(room, conn),
            "connectionId": conn.connection_id,
            "displayName": self._member_display_name(conn),
            "queueMode": "serialized",
            "approved": conn.approved,
            "approvalState": self._member_approval_state(conn),
            "handRaised": conn.hand_raised,
            "queuePosition": 0,
            "lobbyEnabled": room.lobby_enabled,
            "preset": room.preset,
            "agendaSummary": self._agenda_summary(room),
            "events": {
                "roomEvent": True,
                "memberRoleUpdated": True,
                "suggestion": True,
            },
            "roomActions": {
                "listRoomMembers": True,
                "suggestText": True,
                "passDriver": True,
                "addAgendaItem": True,
                "listAgenda": True,
                "resolveAgendaItem": True,
                "setHandRaised": True,
                "nextDriver": True,
            },
        }

        response = self.message_cls(id=message.id, result={"capabilities": capabilities})
        await self._send_rpc(conn.ws, response)

        await self._broadcast_room_event(
            room,
            "member_joined" if conn.approved else "member_pending",
            actor=conn.connection_id,
            queue_depth=room.request_queue.qsize(),
        )

    async def _room_worker(self, room: RoomState) -> None:
        while True:
            queued = await room.request_queue.get()
            try:
                conn = room.members.get(queued.connection_id)
                # Audit note: queued work for disconnected/stale members is dropped
                # before dispatch to avoid cross-routing responses.
                if conn is None or conn.ws.closed:
                    continue

                room.active_connection_id = queued.connection_id
                request_id = self._extract_request_id(queued.message)

                await self._broadcast_room_event(
                    room,
                    "started",
                    request_id=request_id,
                    actor=queued.connection_id,
                    queue_depth=room.request_queue.qsize(),
                )

                try:
                    async with room.dispatch_lock:
                        response = await room.server.dispatch(queued.message)
                    if queued.message.id is not None and not conn.ws.closed:
                        await self._send_rpc(conn.ws, response)
                except Exception as e:
                    logger.exception("Room worker dispatch failed for room %s", room.name)
                    if queued.message.id is not None and not conn.ws.closed:
                        try:
                            await self._send_error_response(
                                conn.ws,
                                request_id=queued.message.id,
                                code=self.rpc_error_cls.INTERNAL_ERROR,
                                message=str(e),
                                data={"error_code": "INTERNAL_ERROR"},
                            )
                        except Exception:
                            logger.debug(
                                "Failed to send worker error response to %s",
                                queued.connection_id,
                            )
                finally:
                    if room.active_connection_id == queued.connection_id:
                        room.active_connection_id = None
                    await self._broadcast_room_event(
                        room,
                        "finished",
                        request_id=request_id,
                        actor=queued.connection_id,
                        queue_depth=room.request_queue.qsize(),
                    )
            finally:
                room.request_queue.task_done()

    async def _handle_suggest_text(self, conn: ConnectionState, room: RoomState, message: Any) -> None:
        """Broadcast a suggestion from any member to all prompter-role members."""
        params = message.params or {}
        text = str(params.get("text", "")).strip()
        if not text:
            if message.id is not None:
                await self._send_rpc(
                    conn.ws,
                    self.message_cls(id=message.id, result={"success": False, "reason": "empty text"}),
                )
            return
        sender = conn.client_name or conn.connection_id
        if room.preset == "review":
            item = await self.add_room_agenda_item(
                room.name,
                text,
                author=sender,
                actor_connection_id=conn.connection_id,
            )
            if message.id is not None:
                await self._send_rpc(
                    conn.ws,
                    self.message_cls(
                        id=message.id,
                        result={
                            "success": True,
                            "mode": "agenda",
                            "item": item,
                            "agendaSummary": self._agenda_summary(room),
                        },
                    ),
                )
            return
        recipients = [
            member
            for member in room.members.values()
            if member.role == "prompter" and member.approved and member.ws is not None and not member.ws.closed
        ]
        if not recipients:
            if message.id is not None:
                await self._send_rpc(
                    conn.ws,
                    self.message_cls(
                        id=message.id,
                        result={"success": False, "reason": "no_active_driver"},
                    ),
                )
            return
        notification = self.message_cls(
            method="poor-cli/suggestion",
            params={"sender": sender, "text": text, "room": room.name},
        )
        for member in recipients:
            await self._send_rpc(member.ws, notification)
        if message.id is not None:
            await self._send_rpc(
                conn.ws,
                self.message_cls(
                    id=message.id,
                    result={"success": True, "mode": "suggestion", "delivered": len(recipients)},
                ),
            )

    async def _cleanup_connection(self, conn: ConnectionState) -> None:
        self.connections.pop(conn.connection_id, None)

        if conn.room_name:
            room = self.rooms.get(conn.room_name)
            if room and conn.connection_id in room.members:
                room.members.pop(conn.connection_id, None)
                room.hand_raise_queue = [
                    queued_id for queued_id in room.hand_raise_queue if queued_id != conn.connection_id
                ]
                promoted_connection_id = None
                if conn.role == "prompter":
                    promoted_connection_id = self._rebalance_room_roles(room, promote_fallback=True)
                self._prune_hand_raise_queue(room)
                if promoted_connection_id is not None:
                    await self._broadcast_member_role_updates(room)
                await self._broadcast_room_event(
                    room,
                    "member_left",
                    actor=conn.connection_id,
                    queue_depth=room.request_queue.qsize(),
                )

    async def _heartbeat_loop(self) -> None:
        while not self._stopped:
            await asyncio.sleep(self.heartbeat_interval_seconds)
            now = time.monotonic()
            stale_connections: List[ConnectionState] = []
            for conn in list(self.connections.values()):
                if conn.ws.closed:
                    stale_connections.append(conn)
                    continue
                if now - conn.last_pong > self.pong_timeout_seconds:
                    stale_connections.append(conn)
                    continue
                try:
                    await conn.ws.ping()
                except Exception:
                    stale_connections.append(conn)

            for conn in stale_connections:
                if not conn.ws.closed:
                    try:
                        await conn.ws.close(code=4000, message=b"Heartbeat timeout")
                    except Exception:
                        pass
                await self._cleanup_connection(conn)

    async def _broadcast_rpc(self, room: RoomState, message: Any) -> None:
        dead_members: List[str] = []
        for connection_id, member in room.members.items():
            if member.ws.closed:
                dead_members.append(connection_id)
                continue
            try:
                await self._send_rpc(member.ws, message)
            except Exception:
                dead_members.append(connection_id)

        for connection_id in dead_members:
            room.members.pop(connection_id, None)
            self.connections.pop(connection_id, None)
        if dead_members:
            self._prune_hand_raise_queue(room)

    async def _broadcast_streaming_chunk(
        self,
        room: RoomState,
        *,
        request_id: str,
        content: str,
        done: bool,
    ) -> None:
        requester_id = room.active_connection_id or ""
        notification = self.message_cls(
            method="poor-cli/streamingChunk",
            params={
                "requestId": request_id,
                "content": content,
                "done": done,
            },
        )
        dead_members: List[str] = []
        for connection_id, member in room.members.items():
            if member.ws.closed:
                dead_members.append(connection_id)
                continue
            should_receive = member.role == "viewer" or connection_id == requester_id
            if not should_receive:
                continue
            try:
                await self._send_rpc(member.ws, notification)
            except Exception:
                dead_members.append(connection_id)

        for connection_id in dead_members:
            room.members.pop(connection_id, None)
            self.connections.pop(connection_id, None)
        if dead_members:
            self._prune_hand_raise_queue(room)

    async def _broadcast_room_event(
        self,
        room: RoomState,
        event_type: str,
        request_id: str = "",
        actor: str = "",
        queue_depth: int = 0,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        member_snapshots = self._room_member_snapshots(room)
        payload = {
            "eventType": event_type,
            "room": room.name,
            "mode": self._room_mode(room),
            "requestId": request_id,
            "actor": actor,
            "queueDepth": queue_depth,
            "memberCount": len(member_snapshots),
            "activeConnectionId": room.active_connection_id or "",
            "lobbyEnabled": room.lobby_enabled,
            "preset": room.preset,
            "agendaSummary": self._agenda_summary(room),
            "members": member_snapshots,
            "details": details or {},
        }
        self._record_activity(
            room,
            event_type=event_type,
            actor=actor,
            request_id=request_id,
            details=payload.get("details"),
        )
        notification = self.message_cls(
            method="poor-cli/roomEvent",
            params=payload,
        )
        await self._broadcast_rpc(room, notification)

    async def _send_rpc(self, ws: web.WebSocketResponse, message: Any) -> None:
        await ws.send_str(message.to_json())

    async def _send_error_response(
        self,
        ws: web.WebSocketResponse,
        request_id: Any,
        code: int,
        message: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> None:
        response = self.message_cls(
            id=request_id,
            error=self.rpc_error_cls.make_error(code, message, data),
        )
        await self._send_rpc(ws, response)

    @staticmethod
    def _extract_request_id(message: Any) -> str:
        if not message.params:
            return ""
        value = message.params.get("requestId", "")
        return str(value)
