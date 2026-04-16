# ruff: noqa: F403,F405
from __future__ import annotations

from poor_cli.server.handler_deps import *
from poor_cli.audit_log import AuditEventType, AuditSeverity, get_audit_logger


class MultiplayerStateMixin:
    def _ensure_host_controls_available(self) -> None:
        """Disallow host lifecycle controls from nested multiplayer room engines."""
        if self._embedded_multiplayer_room:
            raise InvalidParamsError(
                "Host controls are unavailable inside multiplayer room sessions"
            )

    @staticmethod
    def _normalize_multiplayer_room_names(
        raw_rooms: Any,
        fallback_room: str = "",
    ) -> List[str]:
        """Normalize and validate requested room names."""
        candidates: List[str] = []
        if isinstance(raw_rooms, list):
            candidates.extend(str(item) for item in raw_rooms)
        elif isinstance(raw_rooms, str):
            candidates.append(raw_rooms)
        elif raw_rooms is not None:
            raise InvalidParamsError("rooms must be a list of names or a single string")

        if fallback_room.strip():
            candidates.append(fallback_room.strip())

        if not candidates:
            candidates.append("dev")

        normalized: List[str] = []
        for raw_room in candidates:
            room_name = raw_room.strip()
            if not room_name:
                continue
            if len(room_name) > 64:
                raise InvalidParamsError(f"Room name too long: {room_name}")
            if not all(ch.isalnum() or ch in {"-", "_", "."} for ch in room_name):
                raise InvalidParamsError(
                    f"Invalid room name: {room_name}. Use letters, numbers, '-', '_' or '.'."
                )
            if room_name not in normalized:
                normalized.append(room_name)

        if not normalized:
            raise InvalidParamsError("At least one non-empty room name is required")

        return normalized

    @staticmethod
    def _resolve_multiplayer_share_host(bind_host: str) -> str:
        """Resolve a shareable host/IP when binding to wildcard interfaces."""
        host = bind_host.strip()
        if host and host not in {"0.0.0.0", "::"}:
            return host

        try:
            with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_DGRAM)) as sock:
                sock.connect(("8.8.8.8", 80))
                lan_ip = sock.getsockname()[0]
                if lan_ip and not lan_ip.startswith("127."):
                    return lan_ip
        except OSError:
            pass

        return "127.0.0.1"

    @staticmethod
    def _build_multiplayer_ice_servers(config: Config) -> List[Dict[str, Any]]:
        """Build ICE server configuration from loaded config and env-backed TURN creds."""
        multiplayer = config.multiplayer
        ice_servers = [dict(entry) for entry in (multiplayer.ice_servers or [])]

        turn_urls = [str(url).strip() for url in (multiplayer.turn_urls or []) if str(url).strip()]
        if not turn_urls:
            return ice_servers

        username = os.environ.get(multiplayer.turn_username_env, "").strip()
        credential = os.environ.get(multiplayer.turn_credential_env, "").strip()
        if not username or not credential:
            return ice_servers

        turn_entry: Dict[str, Any] = {
            "urls": turn_urls,
            "username": username,
            "credential": credential,
        }
        if multiplayer.turn_realm.strip():
            turn_entry["credentialType"] = "password"
            turn_entry["realm"] = multiplayer.turn_realm.strip()
        ice_servers.append(turn_entry)
        return ice_servers

    @staticmethod
    def _is_port_bindable(bind_host: str, port: int) -> bool:
        """Return True when the given host/port pair can be bound."""
        try:
            address_info = socket.getaddrinfo(bind_host, port, type=socket.SOCK_STREAM)
        except socket.gaierror as e:
            raise InvalidParamsError(f"Invalid bind host: {bind_host}") from e

        for family, socktype, proto, _, sockaddr in address_info:
            with contextlib.closing(socket.socket(family, socktype, proto)) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    sock.bind(sockaddr)
                    return True
                except OSError:
                    continue

        return False

    def _select_multiplayer_port(self, bind_host: str, requested_port: Optional[int]) -> int:
        """Choose a usable host port, preferring 8765+ when unspecified."""
        if requested_port is not None:
            if requested_port <= 0 or requested_port > 65535:
                raise InvalidParamsError("port must be between 1 and 65535")
            if not self._is_port_bindable(bind_host, requested_port):
                raise InvalidParamsError(f"Port {requested_port} is unavailable on {bind_host}")
            return requested_port

        for port_candidate in range(8765, 8865):
            if self._is_port_bindable(bind_host, port_candidate):
                return port_candidate

        raise InvalidParamsError(
            "Unable to find an open port in the 8765-8864 range. Specify `port` explicitly."
        )

    def _compose_host_server_payload(self, *, created: bool, stopped: bool) -> Dict[str, Any]:
        """Build a stable payload describing the active host state."""
        if self._host_server is None:
            return {
                "running": False,
                "created": created,
                "stopped": stopped,
                "rooms": [],
            }

        tokens: Dict[str, Dict[str, str]] = self._host_server.get_room_tokens()
        signaling_url = (
            self._host_public_signaling_url
            or self._host_share_signaling_url
            or self._host_local_signaling_url
        )
        member_count_by_room: Dict[str, int] = {}
        lobby_by_room: Dict[str, bool] = {}
        preset_by_room: Dict[str, str] = {}
        mode_by_room: Dict[str, str] = {}
        agenda_summary_by_room: Dict[str, Dict[str, Any]] = {}
        hands_raised_by_room: Dict[str, int] = {}
        if hasattr(self._host_server, "list_room_members"):
            with contextlib.suppress(Exception):
                member_snapshots = self._host_server.list_room_members(None)
                if isinstance(member_snapshots, list):
                    for room_entry in member_snapshots:
                        if not isinstance(room_entry, dict):
                            continue
                        room_name = str(room_entry.get("name", "")).strip()
                        if not room_name:
                            continue
                        try:
                            member_count_by_room[room_name] = int(room_entry.get("memberCount", 0))
                        except (TypeError, ValueError):
                            member_count_by_room[room_name] = 0
                        lobby_by_room[room_name] = bool(room_entry.get("lobbyEnabled", False))
                        preset_by_room[room_name] = str(room_entry.get("preset", "pairing"))
                        mode_by_room[room_name] = str(room_entry.get("mode", "pair"))
                        agenda_summary_by_room[room_name] = dict(
                            room_entry.get("agendaSummary", {}) or {}
                        )
                        try:
                            hands_raised_by_room[room_name] = int(room_entry.get("handsRaised", 0))
                        except (TypeError, ValueError):
                            hands_raised_by_room[room_name] = 0

        rooms: List[Dict[str, Any]] = []
        for room_name in sorted(tokens.keys()):
            viewer_join_command = ""
            prompter_join_command = ""
            viewer_invite_code = ""
            prompter_invite_code = ""
            if signaling_url:
                if hasattr(self._host_server, "build_room_share_payload"):
                    viewer_share = self._host_server.build_room_share_payload(
                        room_name,
                        "viewer",
                        signaling_url=signaling_url,
                    )
                    if isinstance(viewer_share, dict):
                        viewer_invite_code = str(viewer_share.get("inviteCode", "")).strip()
                        viewer_join_command = (
                            f"poor-cli --remote-invite {viewer_invite_code}"
                            if viewer_invite_code
                            else ""
                        )
                    prompter_share = self._host_server.build_room_share_payload(
                        room_name,
                        "prompter",
                        signaling_url=signaling_url,
                    )
                    if isinstance(prompter_share, dict):
                        prompter_invite_code = str(
                            prompter_share.get("inviteCode", "")
                        ).strip()
                        prompter_join_command = (
                            f"poor-cli --remote-invite {prompter_invite_code}"
                            if prompter_invite_code
                            else ""
                        )

            rooms.append(
                {
                    "name": room_name,
                    "signalingUrl": signaling_url,
                    "viewerJoinCommand": viewer_join_command,
                    "prompterJoinCommand": prompter_join_command,
                    "viewerInviteCode": viewer_invite_code,
                    "prompterInviteCode": prompter_invite_code,
                    "memberCount": member_count_by_room.get(room_name, 0),
                    "lobbyEnabled": lobby_by_room.get(room_name, False),
                    "preset": preset_by_room.get(room_name, "pairing"),
                    "mode": mode_by_room.get(room_name, "pair"),
                    "agendaSummary": agenda_summary_by_room.get(room_name, {}),
                    "handsRaised": hands_raised_by_room.get(room_name, 0),
                }
            )

        return {
            "running": True,
            "created": created,
            "stopped": stopped,
            "bindHost": self._host_bind_host,
            "port": self._host_port,
            "localSignalingUrl": self._host_local_signaling_url,
            "shareSignalingUrl": self._host_share_signaling_url,
            "publicSignalingUrl": self._host_public_signaling_url,
            "signalingUrl": signaling_url,
            "permissionMode": self.permission_mode,
            "ngrokEnabled": self._host_ngrok_enabled,
            "rooms": rooms,
        }

    @staticmethod
    def _find_host_room_payload(payload: Dict[str, Any], room_name: str) -> Optional[Dict[str, Any]]:
        rooms = payload.get("rooms")
        if not isinstance(rooms, list):
            return None
        for room in rooms:
            if isinstance(room, dict) and str(room.get("name", "")).strip() == room_name:
                return room
        return None

    async def _shutdown_host_server_locked(self) -> bool:
        """Stop active host/tunnel and reset state. Call only while holding lock."""
        host = self._host_server
        tunnel = self._host_tunnel
        was_running = host is not None

        self._host_server = None
        self._host_tunnel = None
        self._host_bind_host = ""
        self._host_port = 0
        self._host_local_signaling_url = ""
        self._host_share_signaling_url = ""
        self._host_public_signaling_url = None
        self._host_rooms = []
        self._host_ngrok_enabled = False

        if host is not None:
            await host.stop()
        if tunnel is not None:
            await tunnel.stop()

        return was_running

    async def handle_start_host_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Start an in-process multiplayer host and return join details/tokens.

        Params:
            room: Optional room name shortcut
            rooms: Optional list of room names
            bindHost: Optional bind host (default 0.0.0.0)
            port: Optional port; auto-selects from 8765+ when omitted
            ngrok: Optional bool to launch ngrok helper
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()
        _, config = self._ensure_config_loaded()

        default_bind_host = str(config.multiplayer.signaling_bind_host or "0.0.0.0").strip()
        bind_host = str(params.get("bindHost", default_bind_host)).strip() or default_bind_host
        room_hint = str(params.get("room", "")).strip()
        rooms = self._normalize_multiplayer_room_names(params.get("rooms"), room_hint)

        requested_port: Optional[int] = None
        raw_port = params.get("port")
        if raw_port not in (None, ""):
            try:
                requested_port = int(raw_port)
            except (TypeError, ValueError) as e:
                raise InvalidParamsError("port must be an integer") from e

        enable_ngrok = bool(params.get("ngrok", False))

        async with self._get_host_server_lock():
            if self._host_server is not None:
                return self._compose_host_server_payload(created=False, stopped=False)

            port = self._select_multiplayer_port(bind_host, requested_port)

            from ..multiplayer import MultiplayerHost

            host = MultiplayerHost(
                bind_host=bind_host,
                port=port,
                room_names=rooms,
                server_factory=PoorCLIServer,
                message_cls=JsonRpcMessage,
                rpc_error_cls=JsonRpcError,
                default_permission_mode=self.permission_mode,
                invite_ttl_seconds=config.multiplayer.invite_ttl_seconds,
                owner_name=config.multiplayer.owner_name,
                ice_servers=self._build_multiplayer_ice_servers(config),
                typing_presence_enabled=config.multiplayer.features.typingPresence,
                message_attribution_enabled=config.multiplayer.features.messageAttribution,
                multi_prompter_enabled=config.multiplayer.features.multiPrompter,
                typing_presence_debounce_ms=config.multiplayer.typingPresence.debounceMs,
                typing_presence_broadcast_interval_ms=(
                    config.multiplayer.typingPresence.broadcastIntervalMs
                ),
                diff_voting_enabled=config.multiplayer.features.diffVoting,
                diff_voting_threshold=config.multiplayer.diffVoting.threshold,
                diff_voting_required_voters=config.multiplayer.diffVoting.requiredVoters,
            )
            try:
                await host.start()
            except Exception:
                with contextlib.suppress(Exception):
                    await host.stop()
                raise

            tunnel: Optional[Any] = None
            public_ws_url: Optional[str] = None
            if enable_ngrok:
                from .multiplayer_runtime import NgrokTunnel

                tunnel = NgrokTunnel(f"{bind_host}:{port}")
                try:
                    public_https = await tunnel.start()
                    if public_https:
                        public_ws_url = public_https + "/rpc"
                except Exception as error:
                    self.logger.warning(f"ngrok helper failed while starting host: {error}")

            local_host = "127.0.0.1" if bind_host in {"0.0.0.0", "::"} else bind_host
            share_host = str(config.multiplayer.share_host or "").strip()
            if not share_host:
                share_host = self._resolve_multiplayer_share_host(bind_host)

            self._host_server = host
            self._host_tunnel = tunnel
            self._host_bind_host = bind_host
            self._host_port = port
            self._host_local_signaling_url = f"http://{local_host}:{port}/rpc"
            self._host_share_signaling_url = f"http://{share_host}:{port}/rpc"
            self._host_public_signaling_url = public_ws_url
            self._host_rooms = rooms
            self._host_ngrok_enabled = enable_ngrok

            payload = self._compose_host_server_payload(created=True, stopped=False)
            await self._emit_collaboration_event(
                "host_started",
                {
                    "rooms": rooms,
                    "bindHost": bind_host,
                    "port": port,
                    "shareSignalingUrl": self._host_share_signaling_url,
                },
            )
            return payload

    async def handle_get_host_server_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return current in-process multiplayer host status."""
        del params
        self._ensure_initialized()
        self._ensure_host_controls_available()
        async with self._get_host_server_lock():
            return self._compose_host_server_payload(created=False, stopped=False)

    async def handle_get_collab_summary(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Return a concise collaboration summary for shared status surfaces."""
        del params
        self._ensure_initialized()
        return {"collaboration": self._collaboration_status_payload()}

    async def handle_stop_host_server(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Stop an active in-process multiplayer host if one is running."""
        del params
        self._ensure_initialized()
        self._ensure_host_controls_available()
        async with self._get_host_server_lock():
            active_rooms = list(self._host_rooms)
            was_running = await self._shutdown_host_server_locked()
            payload = self._compose_host_server_payload(created=False, stopped=was_running)
            if was_running:
                await self._emit_collaboration_event(
                    "host_stopped",
                    {
                        "rooms": active_rooms,
                    },
                )
            return payload

    def _host_room_names_locked(self) -> List[str]:
        """Return active host room names (call while holding host lock)."""
        if self._host_server is None:
            return []

        host_rooms = getattr(self._host_server, "rooms", None)
        if isinstance(host_rooms, dict) and host_rooms:
            return sorted(str(name) for name in host_rooms.keys())
        return sorted(str(name) for name in self._host_rooms)

    def _resolve_host_room_name_locked(self, requested_room: str) -> str:
        """Resolve room name for host-member controls (call while holding host lock)."""
        room_names = self._host_room_names_locked()
        if not room_names:
            raise InvalidParamsError("No multiplayer host is currently running")

        normalized = requested_room.strip()
        if normalized:
            if normalized not in room_names:
                raise InvalidParamsError(
                    f"Unknown room `{normalized}`. Available rooms: {', '.join(room_names)}"
                )
            return normalized

        if len(room_names) == 1:
            return room_names[0]
        raise InvalidParamsError(
            "Multiple rooms are active; specify one with `room`."
        )

    @staticmethod
    def _normalize_member_role(raw_role: Any) -> str:
        """Normalize role values used by host-member controls."""
        role_name = str(raw_role or "").strip().lower()
        if role_name in {"viewer", "read", "read-only"}:
            return "viewer"
        if role_name in {"prompter", "writer", "editor", "admin"}:
            return "prompter"
        raise InvalidParamsError("role must be one of: viewer, prompter")

    def _resolve_host_member_reference_locked(self, room_name: str, reference: str) -> str:
        normalized = str(reference or "").strip()
        if not normalized:
            raise InvalidParamsError("Missing connectionId")
        host = self._host_server
        if host is None:
            raise InvalidParamsError("No multiplayer host is currently running")
        if hasattr(host, "resolve_room_member_reference"):
            resolved = host.resolve_room_member_reference(room_name, normalized)
            if resolved:
                return resolved
        return normalized

    def _audit_multiplayer_role_change(
        self,
        *,
        operation: str,
        room: str,
        connection_id: str,
        role: str = "",
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            maybe_core = getattr(self, "_maybe_core", None)
            core = maybe_core() if callable(maybe_core) else None
            audit_logger = getattr(core, "_audit_logger", None) if core is not None else None
            if audit_logger is None:
                audit_logger = get_audit_logger()
            audit_logger.log_event(
                event_type=AuditEventType.CONFIG_CHANGE,
                operation=operation,
                target=f"multiplayer:{room}:{connection_id}",
                details={
                    "room": room,
                    "connection_id": connection_id,
                    "role": role,
                    **(details or {}),
                },
                severity=AuditSeverity.INFO,
                success=True,
            )
        except Exception as e:
            logger.debug("Audit logging failed for multiplayer role change: %s", e)

    def _collab_room_payload_locked(self, requested_room: str = "") -> Dict[str, Any]:
        payload = self._compose_host_server_payload(created=False, stopped=False)
        if self._host_server is None:
            return payload

        member_rooms: Dict[str, Dict[str, Any]] = {}
        if hasattr(self._host_server, "list_room_members"):
            for room_entry in self._host_server.list_room_members(requested_room or None):
                if isinstance(room_entry, dict):
                    member_rooms[str(room_entry.get("name", ""))] = room_entry

        rooms: List[Dict[str, Any]] = []
        for room in payload.get("rooms", []):
            if not isinstance(room, dict):
                continue
            room_name = str(room.get("name", ""))
            if requested_room and room_name != requested_room:
                continue
            merged = dict(room)
            merged.update(member_rooms.get(room_name, {}))
            merged["viewerInviteLink"] = merged.get("viewerJoinCommand") or merged.get("viewerInviteCode") or ""
            merged["prompterInviteLink"] = merged.get("prompterJoinCommand") or merged.get("prompterInviteCode") or ""
            merged["inviteLink"] = merged["prompterInviteLink"] or merged["viewerInviteLink"]
            rooms.append(merged)

        if requested_room and not rooms:
            room_names = self._host_room_names_locked()
            raise InvalidParamsError(
                f"Unknown room `{requested_room}`. Available rooms: {', '.join(room_names)}"
            )

        payload["rooms"] = rooms
        if len(rooms) == 1:
            payload["room"] = rooms[0]
        return payload

    async def handle_list_host_members(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List connected members per room for the active in-process multiplayer host.

        Params:
            room: Optional room name filter.
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                return {"running": False, "rooms": []}

            room_names = self._host_room_names_locked()
            if requested_room and requested_room not in room_names:
                raise InvalidParamsError(
                    f"Unknown room `{requested_room}`. Available rooms: {', '.join(room_names)}"
                )

            host = self._host_server
            if not hasattr(host, "list_room_members"):
                raise RuntimeError("Active host does not support member listing")

            rooms_payload = host.list_room_members(requested_room or None)
            return {"running": True, "rooms": rooms_payload}

    async def handle_set_typing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")
        requested_room = str(params.get("room", "")).strip()
        typing = bool(params.get("typing", False))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not getattr(host, "typing_presence_enabled", False):
                raise InvalidParamsError("typingPresence feature is disabled")
            if not hasattr(host, "set_member_typing"):
                raise RuntimeError("Active host does not support typing presence")
            result = await host.set_member_typing(room_name, connection_id, typing)
            if result is None:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )
            return result

    async def handle_list_presence(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not getattr(host, "typing_presence_enabled", False):
                raise InvalidParamsError("typingPresence feature is disabled")
            if not hasattr(host, "list_room_presence"):
                raise RuntimeError("Active host does not support typing presence")
            result = await host.list_room_presence(room_name)
            if result is None:
                raise InvalidParamsError(f"Unknown room `{room_name}`")
            return result

    async def handle_list_room_queue(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not getattr(host, "multi_prompter_enabled", False):
                raise InvalidParamsError("multiPrompter feature is disabled")
            if not hasattr(host, "list_room_queue"):
                raise RuntimeError("Active host does not support room queues")
            result = host.list_room_queue(room_name)
            if result is None:
                raise InvalidParamsError(f"Unknown room `{room_name}`")
            return result

    async def handle_cancel_queue_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        queue_id = str(params.get("queueId", params.get("queue_id", ""))).strip()
        if not queue_id:
            raise InvalidParamsError("queueId is required")
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not getattr(host, "multi_prompter_enabled", False):
                raise InvalidParamsError("multiPrompter feature is disabled")
            if not hasattr(host, "cancel_room_queue_item"):
                raise RuntimeError("Active host does not support room queues")
            result = await host.cancel_room_queue_item(room_name, queue_id, owner=True)
            if result is None or result.get("reason") == "not_found":
                raise InvalidParamsError(f"Unknown queue item: {queue_id}")
            return result

    async def handle_remove_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove/disconnect a connected member from a host room.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "remove_room_member"):
                raise RuntimeError("Active host does not support member removal")

            removed = await host.remove_room_member(room_name, connection_id)
            if not removed:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "removed": True,
            }

    async def handle_set_host_member_role(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update a connected member role for a host room.

        Params:
            connectionId: Target connection id
            role: viewer | prompter
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        role_name = self._normalize_member_role(params.get("role"))
        requested_room = str(params.get("room", "")).strip()

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "set_room_member_role"):
                raise RuntimeError("Active host does not support role updates")

            try:
                updated = await host.set_room_member_role(room_name, connection_id, role_name)
            except ValueError as error:
                raise InvalidParamsError(str(error)) from error

            if not updated:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )
            self._audit_multiplayer_role_change(
                operation="multiplayer.role.set",
                room=room_name,
                connection_id=connection_id,
                role=role_name,
            )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "role": role_name,
            }

    async def handle_set_host_lobby(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enable/disable host lobby approval mode for a room.

        Params:
            enabled: bool
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        enabled = bool(params.get("enabled", True))
        requested_room = str(params.get("room", "")).strip()

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "set_room_lobby"):
                raise RuntimeError("Active host does not support lobby controls")

            updated = await host.set_room_lobby(room_name, enabled)
            if not updated:
                raise InvalidParamsError(f"Unknown room `{room_name}`")

            return {
                "success": True,
                "room": room_name,
                "lobbyEnabled": enabled,
            }

    async def handle_approve_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Approve a pending room member when lobby mode is enabled.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "approve_room_member"):
                raise RuntimeError("Active host does not support member approvals")

            approved = await host.approve_room_member(room_name, connection_id)
            if not approved:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "approved": True,
            }

    async def handle_deny_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deny/remove a pending room member when lobby mode is enabled.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "deny_room_member"):
                raise RuntimeError("Active host does not support member denial")

            denied = await host.deny_room_member(room_name, connection_id)
            if not denied:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "denied": True,
            }

    async def handle_rotate_host_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Rotate room invite token for a role.

        Params:
            role: viewer | prompter
            room: Optional room name (required if multiple rooms)
            expiresInSeconds: Optional token expiry (seconds)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        role_name = self._normalize_member_role(params.get("role"))
        requested_room = str(params.get("room", "")).strip()
        raw_ttl = params.get("expiresInSeconds")
        ttl_seconds: Optional[int]
        if raw_ttl is None:
            ttl_seconds = None
        else:
            try:
                ttl_seconds = int(raw_ttl)
            except (TypeError, ValueError) as e:
                raise InvalidParamsError("expiresInSeconds must be a positive integer") from e
            if ttl_seconds <= 0:
                raise InvalidParamsError("expiresInSeconds must be a positive integer")

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "rotate_room_token"):
                raise RuntimeError("Active host does not support token rotation")

            try:
                token = await host.rotate_room_token(
                    room_name,
                    role_name,
                    expires_in_seconds=ttl_seconds,
                )
            except ValueError as error:
                raise InvalidParamsError(str(error)) from error

            if not token:
                raise InvalidParamsError(f"Unable to rotate token for room `{room_name}`")

            signaling_url = (
                self._host_public_signaling_url
                or self._host_share_signaling_url
                or self._host_local_signaling_url
            )
            join_command = ""
            invite_code = ""
            expires_at = ""
            if ttl_seconds is not None:
                expires_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
                ).isoformat()
            if signaling_url:
                if hasattr(host, "build_room_share_payload"):
                    share_payload = host.build_room_share_payload(
                        room_name,
                        role_name,
                        signaling_url=signaling_url,
                        expires_in_seconds=ttl_seconds,
                    )
                    if isinstance(share_payload, dict):
                        invite_code = str(share_payload.get("inviteCode", "")).strip()
                        join_command = (
                            f"poor-cli --remote-invite {invite_code}"
                            if invite_code
                            else ""
                        )

            return {
                "success": True,
                "room": room_name,
                "role": role_name,
                "joinCommand": join_command,
                "inviteCode": invite_code,
                "expiresAt": expires_at,
            }

    async def handle_revoke_host_token(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Revoke an invite token or remove a member by connection id.

        Params:
            value: token or connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        value = str(params.get("value", "")).strip()
        if not value:
            raise InvalidParamsError("Missing value (token or connectionId)")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server

            removed_member = False
            resolved_value = self._resolve_host_member_reference_locked(room_name, value)
            if hasattr(host, "remove_room_member"):
                removed_member = await host.remove_room_member(room_name, resolved_value)
                if removed_member:
                    return {
                        "success": True,
                        "room": room_name,
                        "connectionId": resolved_value,
                        "removed": True,
                        "kind": "member",
                    }

            if not hasattr(host, "revoke_room_token"):
                raise RuntimeError("Active host does not support token revocation")

            revoked_token = await host.revoke_room_token(room_name, value)
            if not revoked_token:
                raise InvalidParamsError(
                    f"`{value}` was not found as a connection id or token in room `{room_name}`"
                )

            return {
                "success": True,
                "room": room_name,
                "token": value,
                "revoked": True,
                "kind": "token",
            }

    async def handle_handoff_host_member(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handoff prompter control to a specific member.

        Params:
            connectionId: Target connection id
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("Missing connectionId")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "handoff_room_prompter"):
                raise RuntimeError("Active host does not support role handoff")

            handed_off = await host.handoff_room_prompter(room_name, connection_id)
            if not handed_off:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )
            self._audit_multiplayer_role_change(
                operation="multiplayer.driver.handoff",
                room=room_name,
                connection_id=connection_id,
                role="prompter",
            )

            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "role": "prompter",
                "handoff": True,
            }

    async def handle_pair_start(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Start a pair session with auto-generated 6-char room code."""
        self._ensure_initialized()
        import secrets as _secrets
        short_code = _secrets.token_hex(3)  # 6 hex chars
        lobby = bool(params.get("lobby", False))
        host_result = await self.handle_start_host_server({"room": short_code})
        room_payload = self._find_host_room_payload(host_result, short_code)
        if room_payload is None:
            raise RuntimeError("Host started without returning canonical pair room details")

        invite_code = str(room_payload.get("viewerInviteCode", "")).strip()
        signaling_url = str(
            room_payload.get("signalingUrl")
            or host_result.get("signalingUrl")
            or host_result.get("shareSignalingUrl")
            or host_result.get("publicSignalingUrl")
            or ""
        ).strip()
        if not invite_code or not signaling_url:
            raise RuntimeError("Pair session is missing shareable invite details")
        if lobby:
            try:
                await self.handle_set_host_lobby({"enabled": True, "room": short_code})
            except Exception:
                pass
        return {
            "shortCode": short_code,
            "inviteCode": invite_code,
            "signalingUrl": signaling_url,
            "room": room_payload,
            **host_result,
        }

    async def handle_suggest_text(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Suggest text in local host mode; review rooms promote suggestions into agenda."""
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        text = str(params.get("text", "")).strip()
        if not text:
            raise InvalidParamsError("text is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                return {"success": True, "local": True}
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            room = host.rooms.get(room_name) if hasattr(host, "rooms") else None
            if room is not None and room.preset == "review" and hasattr(host, "add_room_agenda_item"):
                item = await host.add_room_agenda_item(room_name, text, author="host")
                return {
                    "success": True,
                    "room": room_name,
                    "mode": "agenda",
                    "item": item,
                    "agendaSummary": host.list_room_members(room_name)[0].get("agendaSummary", {}),
                }
        return {"success": True, "local": True}

    async def handle_peer_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Broadcast a freeform chat message to all other members of the current host room."""
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        text = str(params.get("text", "")).strip()
        if not text:
            raise InvalidParamsError("text is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                return {"success": False, "reason": "no_host"}
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "broadcast_host_message"):
                return {"success": False, "reason": "unsupported"}
            delivered = await host.broadcast_host_message(room_name, text, sender="host")
            return {"success": True, "room": room_name, "delivered": delivered}

    async def handle_add_agenda_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        text = str(params.get("text", "")).strip()
        if not text:
            raise InvalidParamsError("text is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "add_room_agenda_item"):
                raise RuntimeError("Active host does not support agenda items")
            item = await host.add_room_agenda_item(
                room_name,
                text,
                author=str(params.get("author", "host")).strip() or "host",
            )
            if item is None:
                raise InvalidParamsError(f"Unknown room `{room_name}`")
            room_payload = host.list_room_members(room_name) if hasattr(host, "list_room_members") else []
            agenda_summary = {}
            if room_payload and isinstance(room_payload, list):
                agenda_summary = dict(room_payload[0].get("agendaSummary", {}) or {})
            payload = {
                "success": True,
                "room": room_name,
                "item": item,
                "agendaSummary": agenda_summary,
            }
            await self._emit_collaboration_event(
                "agenda_added",
                {
                    "room": room_name,
                    "itemId": str(item.get("itemId", "")) if isinstance(item, dict) else "",
                    "text": text,
                },
            )
            return payload

    async def handle_list_agenda(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        include_resolved = bool(params.get("includeResolved", True))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "list_room_agenda"):
                raise RuntimeError("Active host does not support agenda items")
            items = host.list_room_agenda(room_name, include_resolved=include_resolved)
            agenda_summary = {}
            if hasattr(host, "list_room_members"):
                room_payload = host.list_room_members(room_name)
                if room_payload and isinstance(room_payload, list):
                    agenda_summary = dict(room_payload[0].get("agendaSummary", {}) or {})
            return {
                "room": room_name,
                "items": items,
                "agendaSummary": agenda_summary,
            }

    async def handle_resolve_agenda_item(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        item_id = str(params.get("itemId", params.get("id", ""))).strip()
        if not item_id:
            raise InvalidParamsError("itemId is required")

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "resolve_room_agenda_item"):
                raise RuntimeError("Active host does not support agenda items")
            item = await host.resolve_room_agenda_item(
                room_name,
                item_id,
                resolved_by=str(params.get("resolvedBy", "host")).strip() or "host",
            )
            if item is None:
                raise InvalidParamsError(f"Agenda item `{item_id}` was not found in room `{room_name}`")
            agenda_summary = {}
            if hasattr(host, "list_room_members"):
                room_payload = host.list_room_members(room_name)
                if room_payload and isinstance(room_payload, list):
                    agenda_summary = dict(room_payload[0].get("agendaSummary", {}) or {})
            payload = {
                "success": True,
                "room": room_name,
                "item": item,
                "agendaSummary": agenda_summary,
            }
            await self._emit_collaboration_event(
                "agenda_resolved",
                {
                    "room": room_name,
                    "itemId": item_id,
                },
            )
            return payload

    async def handle_set_hand_raised(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()
        connection_id = str(params.get("connectionId", "")).strip()
        if not connection_id:
            raise InvalidParamsError("connectionId is required in local host mode")
        raised = bool(params.get("raised", True))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            connection_id = self._resolve_host_member_reference_locked(room_name, connection_id)
            host = self._host_server
            if not hasattr(host, "set_room_member_hand_raised"):
                raise RuntimeError("Active host does not support hand raise state")
            result = await host.set_room_member_hand_raised(room_name, connection_id, raised)
            if result is None:
                raise InvalidParamsError(
                    f"Connection `{connection_id}` was not found in room `{room_name}`"
                )
            return {
                "success": True,
                "room": room_name,
                **result,
            }

    async def handle_next_driver(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        requested_room = str(params.get("room", "")).strip()

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")
            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "handoff_next_driver"):
                raise RuntimeError("Active host does not support next-driver handoff")
            connection_id = await host.handoff_next_driver(room_name)
            if connection_id is None:
                raise InvalidParamsError("No eligible member found to receive driver role")
            self._audit_multiplayer_role_change(
                operation="multiplayer.driver.next",
                room=room_name,
                connection_id=connection_id,
                role="prompter",
            )
            return {
                "success": True,
                "room": room_name,
                "connectionId": connection_id,
                "handoff": True,
            }

    async def handle_pass_driver(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve display name to connection ID and hand off prompter role."""
        self._ensure_initialized()
        self._ensure_host_controls_available()
        display_name = str(params.get("displayName", "")).strip()
        connection_id = str(params.get("connectionId", "")).strip()
        requested_room = str(params.get("room", "")).strip()
        if not connection_id and not display_name:
            return await self.handle_next_driver({"room": requested_room})
        if not connection_id and display_name:
            connection_id = display_name
        return await self.handle_handoff_host_member({
            "connectionId": connection_id,
            "room": requested_room,
        })

    async def handle_collab_room(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        self._ensure_host_controls_available()
        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            return self._collab_room_payload_locked(requested_room)

    async def handle_collab_room_members(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self.handle_list_host_members(params)

    async def handle_collab_room_pass_driver(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self.handle_pass_driver(params)

    async def handle_collab_room_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return await self.handle_list_host_activity(params)

    async def handle_collab_room_get_invite_link(self, params: Dict[str, Any]) -> Dict[str, Any]:
        self._ensure_initialized()
        self._ensure_host_controls_available()
        requested_room = str(params.get("room", "")).strip()
        role = str(params.get("role", "prompter")).strip().lower()
        async with self._get_host_server_lock():
            payload = self._collab_room_payload_locked(requested_room)
            rooms = payload.get("rooms") if isinstance(payload.get("rooms"), list) else []
            if not rooms:
                raise InvalidParamsError("No multiplayer host room is currently running")
            room = rooms[0]
            key = "viewerInviteLink" if role == "viewer" else "prompterInviteLink"
            invite_link = str(room.get(key) or room.get("inviteLink") or "")
            return {
                "success": bool(invite_link),
                "room": room.get("name", ""),
                "role": "viewer" if role == "viewer" else "prompter",
                "inviteLink": invite_link,
            }

    async def handle_set_host_preset(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a room preset for collaboration mode.

        Params:
            preset: pairing | mob | review
            room: Optional room name (required if multiple rooms)
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        preset = str(params.get("preset", "")).strip().lower()
        if preset not in {"pairing", "mob", "review"}:
            raise InvalidParamsError("preset must be one of: pairing, mob, review")

        requested_room = str(params.get("room", "")).strip()
        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "set_room_preset"):
                raise RuntimeError("Active host does not support presets")

            try:
                applied = await host.set_room_preset(room_name, preset)
            except ValueError as error:
                raise InvalidParamsError(str(error)) from error
            if not applied:
                raise InvalidParamsError(f"Unknown room `{room_name}`")

            lobby_enabled = False
            if hasattr(host, "list_room_members"):
                with contextlib.suppress(Exception):
                    room_data = host.list_room_members(room_name)
                    if room_data and isinstance(room_data, list):
                        lobby_enabled = bool(room_data[0].get("lobbyEnabled", False))

            return {
                "success": True,
                "room": room_name,
                "preset": preset,
                "lobbyEnabled": lobby_enabled,
            }

    async def handle_list_host_activity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        List recent multiplayer room activity entries.

        Params:
            room: Optional room name (required if multiple rooms)
            limit: Optional max items (default 50)
            eventType: Optional event type filter
        """
        self._ensure_initialized()
        self._ensure_host_controls_available()

        requested_room = str(params.get("room", "")).strip()
        event_type = str(params.get("eventType", "")).strip()
        raw_limit = params.get("limit", 50)
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError) as e:
            raise InvalidParamsError("limit must be an integer") from e
        limit = max(1, min(limit, 200))

        async with self._get_host_server_lock():
            if self._host_server is None:
                raise InvalidParamsError("No multiplayer host is currently running")

            room_name = self._resolve_host_room_name_locked(requested_room)
            host = self._host_server
            if not hasattr(host, "list_room_activity"):
                raise RuntimeError("Active host does not support activity logs")

            events = host.list_room_activity(room_name, limit, event_type or None)
            return {
                "success": True,
                "room": room_name,
                "events": events,
                "eventType": event_type,
                "count": len(events),
            }
