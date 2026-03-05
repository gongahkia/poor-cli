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
    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.monotonic)
    request_timestamps: Deque[float] = field(default_factory=deque)


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
        for connection_id, member in room.members.items():
            members.append(
                {
                    "connectionId": connection_id,
                    "role": member.role or "unknown",
                    "clientName": member.client_name,
                    "initialized": member.initialized,
                    "connected": not member.ws.closed,
                    "active": room.active_connection_id == connection_id,
                    "approved": member.approved,
                    "joinedAt": member.joined_at or "",
                }
            )
        members.sort(key=lambda entry: entry["connectionId"])
        return members

    def _list_room_member_payload(self, room: RoomState) -> List[Dict[str, Any]]:
        members: List[Dict[str, Any]] = []
        for connection_id, member in room.members.items():
            members.append(
                {
                    "connection_id": connection_id,
                    "role": member.role or "unknown",
                    "connected_at": member.connected_at,
                    "last_active": member.last_active,
                    "is_active_prompter": (
                        member.role == "prompter"
                        and room.active_connection_id == connection_id
                    ),
                }
            )
        members.sort(key=lambda entry: entry["connection_id"])
        return members

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
                    "memberCount": len(members),
                    "members": members,
                    "queueDepth": room.request_queue.qsize(),
                    "activeConnectionId": room.active_connection_id or "",
                    "lobbyEnabled": room.lobby_enabled,
                    "preset": room.preset,
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
        if not enabled:
            for member in room.members.values():
                member.approved = True
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

        try:
            await member.ws.close(code=4003, message=b"Denied by host")
        except Exception:
            pass

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

        for member in room.members.values():
            if member.role == "prompter":
                member.role = "viewer"
        target.role = "prompter"

        for member_id in room.members.keys():
            notification = self.message_cls(
                method="poor-cli/memberRoleUpdated",
                params={
                    "room": room.name,
                    "connectionId": member_id,
                    "role": member.role or "viewer",
                },
            )
            await self._broadcast_rpc(room, notification)

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
        else:
            room.lobby_enabled = True

        await self._broadcast_room_event(
            room,
            "preset_updated",
            details={"preset": normalized, "lobbyEnabled": room.lobby_enabled},
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

        try:
            await member.ws.close(code=4001, message=b"Removed by host")
        except Exception:
            pass

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
        notification = self.message_cls(
            method="poor-cli/memberRoleUpdated",
            params={
                "room": room.name,
                "connectionId": connection_id,
                "role": normalized_role,
            },
        )
        await self._broadcast_rpc(room, notification)
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

        if method == "poor-cli/permissionRes":
            if conn.role != "prompter":
                await self._send_error_response(
                    conn.ws,
                    request_id=message.id,
                    code=self.rpc_error_cls.INTERNAL_ERROR,
                    message="Only prompter role can answer permission prompts",
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

        try:
            await member.ws.close(code=4001, message=b"Kicked by host")
        except Exception:
            pass

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

        capabilities = dict(room.base_capabilities)
        capabilities["multiplayer"] = {
            "enabled": True,
            "room": room_name,
            "role": conn.role,
            "queueMode": "serialized",
            "approved": conn.approved,
            "lobbyEnabled": room.lobby_enabled,
            "preset": room.preset,
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

    async def _cleanup_connection(self, conn: ConnectionState) -> None:
        self.connections.pop(conn.connection_id, None)

        if conn.room_name:
            room = self.rooms.get(conn.room_name)
            if room and conn.connection_id in room.members:
                room.members.pop(conn.connection_id, None)
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
            "requestId": request_id,
            "actor": actor,
            "queueDepth": queue_depth,
            "memberCount": len(member_snapshots),
            "activeConnectionId": room.active_connection_id or "",
            "lobbyEnabled": room.lobby_enabled,
            "preset": room.preset,
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
