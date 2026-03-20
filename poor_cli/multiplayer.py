"""Owner-authoritative multiplayer runtime for poor-cli.

This module hosts room-scoped JSON-RPC sessions over WebRTC DataChannels.
Each room has shared chat state, serialized prompt execution, role-based
access control, and room lifecycle notifications.
"""

from __future__ import annotations

import asyncio
from collections import deque
import contextlib
import json
from pathlib import Path
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

from aiohttp import web

from .exceptions import setup_logger
from .multiplayer_invites import (
    build_owner_fingerprint,
    build_signed_invite,
    verify_signed_invite,
)
from .multiplayer_session import AgendaItem, CollaborationSession, InviteToken

logger = setup_logger(__name__)


@dataclass
class ConnectionState:
    """Connected remote client state."""

    connection_id: str
    ws: Any
    role: Optional[str] = None
    room_name: Optional[str] = None
    initialized: bool = False
    client_name: str = ""
    inline_server: Any = None
    joined_at: Optional[str] = None
    approved: bool = True
    hand_raised: bool = False
    peer_key: Optional[str] = None
    connected_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    request_timestamps: Deque[float] = field(default_factory=deque)


class DataChannelTransport:
    """A minimal send/close wrapper over a WebRTC data channel."""

    def __init__(self, channel: Any):
        self._channel = channel

    @property
    def closed(self) -> bool:
        return str(getattr(self._channel, "readyState", "closed")) != "open"

    async def send_str(self, payload: str) -> None:
        if self.closed:
            raise ConnectionError("data channel is not open")
        self._channel.send(payload)

    async def close(self, code: int = 1000, message: bytes = b"") -> None:
        del code, message
        if not self.closed:
            self._channel.close()

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
    persist_path: Optional[str] = None  # path to persist room state
    session: CollaborationSession = field(init=False, repr=False)


class RoomPersistence:
    """Persist/restore room state to .poor-cli/rooms/."""
    ROOMS_DIR = ".poor-cli/rooms"

    def __init__(self, workspace_root: Optional[Path] = None):
        self.workspace_root = workspace_root or Path.cwd()
        self.rooms_dir = self.workspace_root / self.ROOMS_DIR

    def save_room(self, room: RoomState) -> None:
        """Save room metadata (not connections) to disk."""
        self.rooms_dir.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {
            "name": room.name,
            "tokens": [
                {"token": t.token, "role": t.role, "expires_at": t.expires_at}
                for t in room.tokens.values()
            ],
            "chat_history": getattr(room, "chat_history", []),
            "agenda": [item.to_payload() for item in room.agenda],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self.rooms_dir / f"{room.name}.json"
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def load_room(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Load saved room metadata. Returns None if not found."""
        path = self.rooms_dir / f"{room_name}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def list_saved_rooms(self) -> List[str]:
        """List room names with saved state."""
        if not self.rooms_dir.is_dir():
            return []
        return [p.stem for p in sorted(self.rooms_dir.glob("*.json"))]

    def delete_room(self, room_name: str) -> None:
        """Delete saved room state."""
        path = self.rooms_dir / f"{room_name}.json"
        if path.is_file():
            path.unlink()


class MultiplayerHost:
    """Owner signaling host for multiplayer poor-cli sessions."""

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
        requests_per_minute: int = 10,
        invite_secret: Optional[str] = None,
        invite_ttl_seconds: int = 900,
        owner_name: str = "",
        ice_servers: Optional[List[Dict[str, Any]]] = None,
    ):
        self.bind_host = bind_host
        self.port = port
        self.server_factory = server_factory
        self.message_cls = message_cls
        self.rpc_error_cls = rpc_error_cls
        self.default_permission_mode = default_permission_mode
        self.requests_per_minute = max(1, requests_per_minute)
        self.invite_secret = invite_secret or secrets.token_urlsafe(32)
        self.invite_ttl_seconds = max(1, invite_ttl_seconds)
        self.owner_name = owner_name.strip() or "owner"
        self.owner_id = f"owner-{uuid.uuid4().hex[:12]}"
        self.owner_fingerprint = build_owner_fingerprint(self.invite_secret)
        self.ice_servers = [dict(entry) for entry in (ice_servers or [])]

        self.rooms: Dict[str, RoomState] = {}
        self.connections: Dict[str, ConnectionState] = {}
        self._runner: Optional[web.AppRunner] = None
        self._site: Optional[web.TCPSite] = None
        self._app: Optional[web.Application] = None
        self._stopped = False
        self._peer_connections: Dict[str, Any] = {}

        normalized_rooms = [name.strip() for name in room_names if name and name.strip()]
        if not normalized_rooms:
            normalized_rooms = ["default"]

        for room_name in normalized_rooms:
            self.rooms[room_name] = self._create_room(room_name)

    def build_room_share_payload(
        self,
        room_name: str,
        role: str,
        *,
        signaling_url: str,
        expires_in_seconds: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return None

        normalized_role = role.strip().lower()
        if normalized_role not in {"viewer", "prompter"}:
            raise ValueError("role must be viewer or prompter")

        active_tokens = room.session.active_tokens()
        token = str(active_tokens.get(normalized_role, "")).strip()
        if not token:
            return None

        ttl_seconds = expires_in_seconds
        if ttl_seconds is None or ttl_seconds <= 0:
            ttl_seconds = self.invite_ttl_seconds
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        ).replace(microsecond=0).isoformat()

        payload = {
            "signalingUrl": signaling_url,
            "sessionId": room_name,
            "role": normalized_role,
            "token": token,
            "expiresAt": expires_at,
            "ownerId": self.owner_id,
            "ownerName": self.owner_name,
            "ownerFingerprint": self.owner_fingerprint,
            "iceServers": self.ice_servers,
        }
        invite_code = build_signed_invite(payload, secret=self.invite_secret)
        return {
            "role": normalized_role,
            "token": token,
            "inviteCode": invite_code,
            "expiresAt": expires_at,
            "signalingUrl": signaling_url,
            "sessionId": room_name,
            "ownerId": self.owner_id,
            "ownerName": self.owner_name,
            "ownerFingerprint": self.owner_fingerprint,
            "iceServers": self.ice_servers,
        }

    @staticmethod
    async def _wait_for_ice_gathering_complete(peer_connection: Any, *, timeout: float = 5.0) -> None:
        if str(getattr(peer_connection, "iceGatheringState", "")) == "complete":
            return

        loop = asyncio.get_running_loop()
        done = loop.create_future()

        @peer_connection.on("icegatheringstatechange")
        def _on_ice_gathering_state_change() -> None:
            if str(getattr(peer_connection, "iceGatheringState", "")) == "complete":
                if not done.done():
                    done.set_result(None)

        await asyncio.wait_for(done, timeout=timeout)

    def _build_rtc_configuration(self) -> Any:
        try:
            from aiortc import RTCConfiguration, RTCIceServer
        except ImportError as error:
            raise RuntimeError(
                "P2P multiplayer requires aiortc. Install dependencies with: pip install -r requirements.txt"
            ) from error

        ice_servers = []
        for entry in self.ice_servers:
            urls = entry.get("urls", [])
            if isinstance(urls, str):
                urls = [urls]
            if not isinstance(urls, list) or not urls:
                continue
            kwargs: Dict[str, Any] = {"urls": urls}
            username = str(entry.get("username", "")).strip()
            credential = str(entry.get("credential", "")).strip()
            if username:
                kwargs["username"] = username
            if credential:
                kwargs["credential"] = credential
            ice_servers.append(RTCIceServer(**kwargs))
        return RTCConfiguration(iceServers=ice_servers)

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
        room.session = CollaborationSession(room, is_member_closed=lambda member: member.ws.closed)

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
        return CollaborationSession.now_iso()

    @staticmethod
    def _room_mode(room: RoomState) -> str:
        return room.session.room_mode()

    @staticmethod
    def _member_display_name(member: ConnectionState) -> str:
        return CollaborationSession.member_display_name(member)

    @staticmethod
    def _member_approval_state(member: ConnectionState) -> str:
        return CollaborationSession.member_approval_state(member)

    def _member_ui_role(self, room: RoomState, member: ConnectionState) -> str:
        return room.session.member_ui_role(member)

    @staticmethod
    def _ordered_member_items(room: RoomState) -> List[tuple[str, ConnectionState]]:
        return room.session.ordered_member_items()

    def _agenda_summary(self, room: RoomState) -> Dict[str, Any]:
        return room.session.agenda_summary()

    @staticmethod
    def _is_token_expired(invite: InviteToken) -> bool:
        return CollaborationSession.is_token_expired(invite)

    def _room_member_snapshots(self, room: RoomState) -> List[Dict[str, Any]]:
        return room.session.room_member_snapshots()

    def _list_room_member_payload(self, room: RoomState) -> List[Dict[str, Any]]:
        return room.session.list_room_member_payload()

    def _pick_room_prompter(
        self,
        room: RoomState,
        *,
        preferred_connection_id: Optional[str] = None,
        promote_fallback: bool = False,
    ) -> Optional[str]:
        return room.session.pick_room_prompter(
            preferred_connection_id=preferred_connection_id,
            promote_fallback=promote_fallback,
        )

    def _rebalance_room_roles(
        self,
        room: RoomState,
        *,
        preferred_connection_id: Optional[str] = None,
        promote_fallback: bool = False,
    ) -> Optional[str]:
        return room.session.rebalance_room_roles(
            preferred_connection_id=preferred_connection_id,
            promote_fallback=promote_fallback,
        )

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
        room.session.record_activity(
            event_type=event_type,
            actor=actor,
            request_id=request_id,
            details=details,
        )

    @staticmethod
    def _prune_hand_raise_queue(room: RoomState) -> None:
        room.session.prune_hand_raise_queue()

    def resolve_room_member_reference(self, room_name: str, reference: str) -> Optional[str]:
        room = self.rooms.get(room_name)
        if room is None:
            return None
        return room.session.resolve_member_reference(reference)

    def list_room_agenda(
        self,
        room_name: str,
        *,
        include_resolved: bool = True,
    ) -> List[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return []
        return room.session.list_room_agenda(include_resolved=include_resolved)

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
        item = room.session.add_agenda_item(text, author=author)
        await self._broadcast_room_event(
            room,
            "agenda_added",
            actor=actor_connection_id,
            queue_depth=room.request_queue.qsize(),
            details={"agendaItem": item},
        )
        return item

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
        item = room.session.resolve_agenda_item(item_id, resolved_by=resolved_by)
        if item is None:
            return None
        await self._broadcast_room_event(
            room,
            "agenda_resolved",
            actor=actor_connection_id,
            queue_depth=room.request_queue.qsize(),
            details={"agendaItem": item},
        )
        return item

    async def set_room_member_hand_raised(
        self,
        room_name: str,
        connection_id: str,
        raised: bool,
    ) -> Optional[Dict[str, Any]]:
        room = self.rooms.get(room_name)
        if room is None:
            return None
        result = room.session.set_member_hand_raised(connection_id, raised)
        if result is None:
            return None
        await self._broadcast_room_event(
            room,
            "hand_raised" if result.get("handRaised") else "hand_lowered",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
            details=result,
        )
        return result

    async def handoff_next_driver(
        self,
        room_name: str,
        *,
        actor_connection_id: str = "",
    ) -> Optional[str]:
        room = self.rooms.get(room_name)
        if room is None:
            return None
        next_connection_id = room.session.handoff_next_driver(
            actor_connection_id=actor_connection_id,
        )
        if next_connection_id is None:
            return None
        await self._broadcast_member_role_updates(room)
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
            output[room_name] = room.session.active_tokens()
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

            output.append(room.session.room_snapshot(queue_depth=room.request_queue.qsize()))
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
        return room.session.list_room_activity(limit=limit, event_type=event_type)

    async def set_room_lobby(self, room_name: str, enabled: bool) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False
        roles_rebalanced = room.session.set_room_lobby(enabled)
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
        approved, promoted_connection_id = room.session.approve_room_member(connection_id)
        if not approved:
            return False
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
        member, promoted_connection_id = room.session.pop_room_member(
            connection_id,
            promote_fallback=True,
        )
        if member is None:
            return False

        self.connections.pop(connection_id, None)

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
        new_token = room.session.rotate_room_token(
            role,
            expires_in_seconds=expires_in_seconds,
        )
        await self._broadcast_room_event(
            room,
            "token_rotated",
            details={"role": role.strip().lower()},
            queue_depth=room.request_queue.qsize(),
        )
        return new_token

    async def revoke_room_token(self, room_name: str, token: str) -> bool:
        room = self.rooms.get(room_name)
        if room is None:
            return False
        invite = room.session.revoke_room_token(token)
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
        if not room.session.handoff_room_prompter(connection_id):
            return False
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
        normalized = room.session.set_room_preset(preset)

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
        member, promoted_connection_id = room.session.pop_room_member(
            connection_id,
            promote_fallback=True,
        )
        if member is None:
            return False

        self.connections.pop(connection_id, None)

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
        if not room.session.set_room_member_role(connection_id, role):
            return False
        await self._broadcast_member_role_updates(room)
        await self._broadcast_room_event(
            room,
            "member_role_updated",
            actor=connection_id,
            queue_depth=room.request_queue.qsize(),
        )
        return True

    async def start(self) -> None:
        """Start the HTTP signaling host."""
        app = web.Application()
        app.router.add_post("/rpc", self._handle_signaling_rpc)
        app.router.add_get("/health", self._handle_health)

        self._app = app
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, host=self.bind_host, port=self.port)
        await self._site.start()
        logger.info("Multiplayer signaling host listening on http://%s:%s/rpc", self.bind_host, self.port)

    async def _handle_signaling_rpc(self, request: web.Request) -> web.Response:
        """Handle owner-side signaling/bootstrap requests."""
        try:
            payload = await request.json()
        except Exception:
            return web.json_response(
                {"ok": False, "error": "invalid_json"},
                status=400,
            )

        if not isinstance(payload, dict):
            return web.json_response(
                {"ok": False, "error": "invalid_payload"},
                status=400,
            )

        action = str(payload.get("action", "")).strip().lower()
        if action == "connect":
            return await self._handle_signaling_connect(payload)
        return web.json_response(
            {
                "ok": False,
                "error": "unsupported_action",
                "supportedActions": ["connect"],
            },
            status=400,
        )

    async def _handle_signaling_connect(self, payload: Dict[str, Any]) -> web.Response:
        room_name = str(payload.get("room", "")).strip()
        token = str(payload.get("token", "")).strip()
        invite_code = str(payload.get("invite", "")).strip()
        client_name = str(payload.get("clientName", "")).strip()
        offer_payload = payload.get("offer")

        if invite_code:
            try:
                invite_payload = verify_signed_invite(invite_code, secret=self.invite_secret)
            except ValueError as error:
                return web.json_response(
                    {"ok": False, "error": "invalid_invite", "message": str(error)},
                    status=403,
                )
            room_name = str(invite_payload.get("sessionId", "")).strip()
            token = str(invite_payload.get("token", "")).strip()

        if not room_name or not token:
            return web.json_response(
                {"ok": False, "error": "invalid_multiplayer_auth"},
                status=403,
            )

        room = self.rooms.get(room_name)
        invite = room.tokens.get(token) if room else None
        if room is None or invite is None or self._is_token_expired(invite):
            if room is not None and invite is not None and self._is_token_expired(invite):
                room.tokens.pop(token, None)
            return web.json_response(
                {"ok": False, "error": "invalid_multiplayer_auth"},
                status=403,
            )

        if not isinstance(offer_payload, dict):
            return web.json_response(
                {"ok": False, "error": "invalid_offer"},
                status=400,
            )

        offer_type = str(offer_payload.get("type", "")).strip()
        offer_sdp = str(offer_payload.get("sdp", "")).strip()
        if offer_type != "offer" or not offer_sdp:
            return web.json_response(
                {"ok": False, "error": "invalid_offer"},
                status=400,
            )

        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription
        except ImportError as error:
            return web.json_response(
                {
                    "ok": False,
                    "error": "missing_aiortc",
                    "message": str(error),
                },
                status=500,
            )

        peer_connection = RTCPeerConnection(configuration=self._build_rtc_configuration())
        peer_key = f"peer-{uuid.uuid4().hex[:12]}"
        self._peer_connections[peer_key] = peer_connection
        connection_ref: Dict[str, ConnectionState] = {}

        @peer_connection.on("datachannel")
        def _on_datachannel(channel: Any) -> None:
            connection_id = uuid.uuid4().hex[:12]
            conn = ConnectionState(
                connection_id=connection_id,
                ws=DataChannelTransport(channel),
                client_name=client_name,
                peer_key=peer_key,
            )
            self.connections[connection_id] = conn
            connection_ref["conn"] = conn

            @channel.on("message")
            def _on_message(data: Any) -> None:
                asyncio.create_task(self._handle_datachannel_message(conn, data))

            @channel.on("close")
            def _on_close() -> None:
                asyncio.create_task(self._cleanup_connection(conn))

        @peer_connection.on("connectionstatechange")
        async def _on_connection_state_change() -> None:
            if str(getattr(peer_connection, "connectionState", "")) in {
                "failed",
                "closed",
                "disconnected",
            }:
                conn = connection_ref.get("conn")
                if conn is not None:
                    await self._cleanup_connection(conn)
                self._peer_connections.pop(peer_key, None)
                with contextlib.suppress(Exception):
                    await peer_connection.close()

        try:
            await peer_connection.setRemoteDescription(
                RTCSessionDescription(sdp=offer_sdp, type=offer_type)
            )
            answer = await peer_connection.createAnswer()
            await peer_connection.setLocalDescription(answer)
            await self._wait_for_ice_gathering_complete(peer_connection)
        except Exception as error:
            self._peer_connections.pop(peer_key, None)
            with contextlib.suppress(Exception):
                await peer_connection.close()
            logger.exception("Failed to establish P2P signaling for room %s", room_name)
            return web.json_response(
                {"ok": False, "error": "signaling_failed", "message": str(error)},
                status=500,
            )

        local_description = getattr(peer_connection, "localDescription", None)
        if local_description is None:
            self._peer_connections.pop(peer_key, None)
            with contextlib.suppress(Exception):
                await peer_connection.close()
            return web.json_response(
                {"ok": False, "error": "signaling_failed"},
                status=500,
            )

        return web.json_response(
            {
                "ok": True,
                "room": room_name,
                "role": invite.role,
                "transport": "webrtc-datachannel",
                "answer": {
                    "type": str(getattr(local_description, "type", "answer")),
                    "sdp": str(getattr(local_description, "sdp", "")),
                },
                "ownerId": self.owner_id,
                "ownerName": self.owner_name,
                "ownerFingerprint": self.owner_fingerprint,
                "iceServers": self.ice_servers,
            }
        )

    async def _handle_datachannel_message(self, conn: ConnectionState, payload: Any) -> None:
        if payload is None:
            return
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8", errors="ignore")
        if not isinstance(payload, str):
            return

        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            await self._send_error_response(
                conn.ws,
                request_id=None,
                code=self.rpc_error_cls.PARSE_ERROR,
                message="Invalid JSON",
                data={"error_code": "PARSE_ERROR"},
            )
            return

        if not isinstance(decoded, dict):
            await self._send_error_response(
                conn.ws,
                request_id=None,
                code=self.rpc_error_cls.INVALID_REQUEST,
                message="JSON-RPC payload must be an object",
                data={"error_code": "INVALID_REQUEST"},
            )
            return

        message = self.message_cls.from_dict(decoded)
        await self._handle_message(conn, message)

    async def stop(self) -> None:
        """Stop host and workers."""
        if self._stopped:
            return
        self._stopped = True

        for room in self.rooms.values():
            if room.worker_task:
                room.worker_task.cancel()

        for room in self.rooms.values():
            if room.worker_task:
                try:
                    await room.worker_task
                except asyncio.CancelledError:
                    pass

        for conn in list(self.connections.values()):
            try:
                await conn.ws.close()
            except Exception:
                pass

        for peer_connection in list(self._peer_connections.values()):
            with contextlib.suppress(Exception):
                await peer_connection.close()
        self._peer_connections.clear()

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
                "transport": "webrtc-datachannel",
                "signaling": True,
            }
        )

    async def _handle_message(self, conn: ConnectionState, message: Any) -> None:
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

        member, promoted_connection_id = room.session.pop_room_member(
            target_connection_id,
            promote_fallback=True,
        )
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
        if conn.peer_key:
            peer_connection = self._peer_connections.pop(conn.peer_key, None)
            if peer_connection is not None:
                with contextlib.suppress(Exception):
                    await peer_connection.close()

        if not conn.room_name:
            return

        room = self.rooms.get(conn.room_name)
        if room is None:
            return

        member, promoted_connection_id = room.session.pop_room_member(
            conn.connection_id,
            promote_fallback=True,
        )
        if member is None:
            return

        if promoted_connection_id is not None:
            await self._broadcast_member_role_updates(room)
        await self._broadcast_room_event(
            room,
            "member_left",
            actor=conn.connection_id,
            queue_depth=room.request_queue.qsize(),
        )

    async def _broadcast_rpc(self, room: RoomState, message: Any) -> None:
        dead_members: List[str] = []
        for connection_id, member in list(room.members.items()):
            if member.ws.closed:
                dead_members.append(connection_id)
                continue
            try:
                await self._send_rpc(member.ws, message)
            except Exception:
                dead_members.append(connection_id)

        for connection_id in dict.fromkeys(dead_members):
            member = room.members.get(connection_id) or self.connections.get(connection_id)
            if member is None:
                continue
            await self._cleanup_connection(member)

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
        for connection_id, member in list(room.members.items()):
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

        for connection_id in dict.fromkeys(dead_members):
            member = room.members.get(connection_id) or self.connections.get(connection_id)
            if member is None:
                continue
            await self._cleanup_connection(member)

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

    async def _send_rpc(self, ws: Any, message: Any) -> None:
        await ws.send_str(message.to_json())

    async def _send_error_response(
        self,
        ws: Any,
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
