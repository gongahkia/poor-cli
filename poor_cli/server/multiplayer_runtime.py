"""Multiplayer bridge and host helpers for the server package."""

from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import sys
from typing import Any, Dict, List, Optional

from ..config import ConfigManager
from ..exceptions import setup_logger
from ..multiplayer_invites import decode_bridge_invite_payload
from .runtime import PoorCLIServer
from .types import JsonRpcError, JsonRpcMessage

logger = setup_logger(__name__)


class NgrokTunnel:
    """Helper for launching ngrok and extracting a public URL."""

    def __init__(self, target_addr: str):
        self.target_addr = target_addr
        self.process: Optional[asyncio.subprocess.Process] = None
        self.public_url: Optional[str] = None

    async def start(self, timeout_seconds: float = 12.0) -> Optional[str]:
        """Start ngrok and wait for a public HTTPS URL."""
        if shutil.which("ngrok") is None:
            logger.warning("ngrok not found in PATH; tunnel disabled")
            return None

        self.process = await asyncio.create_subprocess_exec(
            "ngrok",
            "http",
            self.target_addr,
            "--log=stdout",
            "--log-format=json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        if self.process.stdout is None:
            logger.warning("ngrok stdout unavailable; tunnel URL could not be determined")
            return None

        deadline = asyncio.get_event_loop().time() + timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            remaining = max(deadline - asyncio.get_event_loop().time(), 0.05)
            try:
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError:
                break

            if not line:
                break

            text = line.decode("utf-8", errors="ignore").strip()
            if not text:
                continue

            url = None
            try:
                payload = json.loads(text)
                if isinstance(payload, dict):
                    url = payload.get("url")
                    if not url:
                        nested = payload.get("obj")
                        if isinstance(nested, dict):
                            url = nested.get("url")
            except json.JSONDecodeError:
                pass

            if isinstance(url, str) and url.startswith("https://"):
                self.public_url = url
                logger.info(f"ngrok tunnel ready: {url}")
                return url

        logger.warning("Timed out waiting for ngrok public URL")
        return None

    async def stop(self) -> None:
        """Terminate ngrok process if running."""
        if self.process is None:
            return

        if self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.kill()
                with contextlib.suppress(Exception):
                    await self.process.wait()

        self.process = None


def _print_multiplayer_join_hints(
    signaling_url: str,
    share_payloads: Dict[str, Dict[str, Any]],
) -> None:
    """Print host-local invite-based join instructions."""
    print("\npoor-cli multiplayer host is ready.", file=sys.stderr)
    print(f"Signaling endpoint: {signaling_url}", file=sys.stderr)
    print("", file=sys.stderr)
    for room_name in sorted(share_payloads.keys()):
        room_payload = share_payloads[room_name]
        viewer_invite = str(room_payload.get("viewerInviteCode", ""))
        prompter_invite = str(room_payload.get("prompterInviteCode", ""))
        print(f"Room: {room_name}", file=sys.stderr)
        if viewer_invite:
            print(f"  viewer invite:   {viewer_invite}", file=sys.stderr)
        if prompter_invite:
            print(f"  prompter invite: {prompter_invite}", file=sys.stderr)
        print(
            f"  TUI join: poor-cli --remote-invite {prompter_invite or viewer_invite}",
            file=sys.stderr,
        )
        print(
            "  Neovim: multiplayer={ enabled=true, invite='"
            + (prompter_invite or viewer_invite)
            + "' }",
            file=sys.stderr,
        )
        print("", file=sys.stderr)


def _decode_bridge_invite(invite_code: str) -> Dict[str, Any]:
    invite = str(invite_code or "").strip()
    if not invite:
        raise RuntimeError("Invite code is required")

    try:
        return decode_bridge_invite_payload(invite)
    except ValueError as error:
        message = str(error).strip()
        if message == "Invite signaling URL must start with http:// or https://":
            raise RuntimeError(message) from error
        raise RuntimeError("Invalid invite code") from error


async def _run_stdio_bridge(invite_code: str = "") -> None:
    """Run a stdio <-> P2P DataChannel JSON-RPC bridge."""
    try:
        import aiohttp
    except ImportError as e:
        raise RuntimeError(
            "Bridge mode requires aiohttp. Install the current package dependencies in this environment and retry."
        ) from e
    try:
        from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
    except ImportError as e:
        raise RuntimeError(
            "Bridge mode requires aiortc. Install with: pip install 'poor-cli[multiplayer]'"
        ) from e

    bootstrap = _decode_bridge_invite(invite_code)
    url = bootstrap["signaling_url"]
    room = bootstrap["room"]
    token = bootstrap["token"]
    bootstrap_invite = bootstrap["invite"]
    ice_server_payloads = bootstrap["ice_servers"]
    if not url or not room or not token:
        raise RuntimeError("Invite code is missing signaling url, room, or token")

    io_server = PoorCLIServer()
    signaling_url = url
    logger.info(f"Starting stdio P2P bridge via {signaling_url} (room={room})")

    rtc_ice_servers = []
    for entry in ice_server_payloads:
        if not isinstance(entry, dict):
            continue
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
        rtc_ice_servers.append(RTCIceServer(**kwargs))

    peer_connection = RTCPeerConnection(
        configuration=RTCConfiguration(iceServers=rtc_ice_servers)
    )
    data_channel = peer_connection.createDataChannel("poor-cli", ordered=True)
    channel_open = asyncio.Event()
    stdin_eof = asyncio.Event()

    async def _wait_for_ice_complete() -> None:
        if str(getattr(peer_connection, "iceGatheringState", "")) == "complete":
            return
        done = asyncio.get_running_loop().create_future()

        @peer_connection.on("icegatheringstatechange")
        def _on_ice_state_change() -> None:
            if str(getattr(peer_connection, "iceGatheringState", "")) == "complete":
                if not done.done():
                    done.set_result(None)

        await asyncio.wait_for(done, timeout=5.0)

    @data_channel.on("open")
    def _on_channel_open() -> None:
        channel_open.set()

    @data_channel.on("message")
    def _on_channel_message(raw: Any) -> None:
        async def _forward() -> None:
            text = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw
            if not isinstance(text, str):
                return
            try:
                payload = json.loads(text)
            except json.JSONDecodeError:
                logger.warning("Bridge received non-JSON datachannel payload")
                return
            if not isinstance(payload, dict):
                logger.warning("Bridge received non-object datachannel payload")
                return
            rpc_msg = JsonRpcMessage.from_dict(payload)
            await io_server.write_message_stdio(rpc_msg)

        asyncio.create_task(_forward())

    @peer_connection.on("connectionstatechange")
    async def _on_connection_state_change() -> None:
        if str(getattr(peer_connection, "connectionState", "")) in {"failed", "closed", "disconnected"}:
            if not stdin_eof.is_set():
                logger.info("P2P bridge connection state changed to %s", peer_connection.connectionState)

    offer = await peer_connection.createOffer()
    await peer_connection.setLocalDescription(offer)
    await _wait_for_ice_complete()

    async with aiohttp.ClientSession() as session:
        async with session.post(
            signaling_url,
            json={
                "action": "connect",
                "room": room,
                "token": token,
                "invite": bootstrap_invite,
                "clientName": "stdio-bridge",
                "offer": {
                    "type": str(getattr(peer_connection.localDescription, "type", "offer")),
                    "sdp": str(getattr(peer_connection.localDescription, "sdp", "")),
                },
            },
        ) as response:
            if response.status >= 400:
                text = await response.text()
                raise RuntimeError(f"Signaling request failed ({response.status}): {text}")
            data = await response.json()

        if not isinstance(data, dict) or not data.get("ok"):
            raise RuntimeError(f"Signaling request failed: {data}")

        answer = data.get("answer")
        if not isinstance(answer, dict):
            raise RuntimeError("Signaling response did not include an answer")

        await peer_connection.setRemoteDescription(
            RTCSessionDescription(
                sdp=str(answer.get("sdp", "")),
                type=str(answer.get("type", "answer")),
            )
        )

        await asyncio.wait_for(channel_open.wait(), timeout=10.0)

        async def _stdio_to_channel() -> None:
            while True:
                rpc_msg = await io_server.read_message_stdio()
                if rpc_msg is None:
                    stdin_eof.set()
                    break

                if rpc_msg.method == "initialize":
                    params = dict(rpc_msg.params or {})
                    params.setdefault("room", room)
                    params.setdefault("inviteToken", token)
                    params.setdefault("clientName", "stdio-bridge")
                    rpc_msg.params = params

                data_channel.send(rpc_msg.to_json())

        stdio_reader = asyncio.create_task(
            _stdio_to_channel(),
            name="poor-cli-bridge-stdio-reader",
        )

        try:
            await stdio_reader
            if stdin_eof.is_set():
                drain_deadline = asyncio.get_event_loop().time() + 0.25
                while (
                    str(getattr(data_channel, "readyState", "closed")) == "open"
                    and asyncio.get_event_loop().time() < drain_deadline
                ):
                    await asyncio.sleep(0.01)
        finally:
            if not stdio_reader.done():
                stdio_reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await stdio_reader
            with contextlib.suppress(Exception):
                data_channel.close()
            with contextlib.suppress(Exception):
                await peer_connection.close()


async def _run_multiplayer_host(
    bind_host: str,
    port: int,
    rooms: List[str],
    permission_mode: str,
    enable_ngrok: bool,
    turn_urls: Optional[List[str]] = None,
) -> None:
    """Run multiplayer signaling host mode."""
    from ..multiplayer import MultiplayerHost

    config = ConfigManager().load()
    if turn_urls:
        existing = list(config.multiplayer.turn_urls or [])
        existing.extend(url.strip() for url in turn_urls if url.strip())
        config.multiplayer.turn_urls = existing
        logger.info("TURN URLs from CLI: %s", turn_urls)
    share_host = str(config.multiplayer.share_host or "").strip()
    if not share_host:
        share_host = PoorCLIServer._resolve_multiplayer_share_host(bind_host)
    host = MultiplayerHost(
        bind_host=bind_host,
        port=port,
        room_names=rooms,
        server_factory=PoorCLIServer,
        message_cls=JsonRpcMessage,
        rpc_error_cls=JsonRpcError,
        default_permission_mode=permission_mode,
        invite_ttl_seconds=config.multiplayer.invite_ttl_seconds,
        owner_name=config.multiplayer.owner_name,
        ice_servers=PoorCLIServer._build_multiplayer_ice_servers(config),
    )

    tunnel: Optional[NgrokTunnel] = None
    await host.start()
    share_signaling_url = f"http://{share_host}:{port}/rpc"
    initial_payload = {
        "rooms": [
            {
                "name": room_name,
                "viewerInviteCode": (
                    host.build_room_share_payload(
                        room_name,
                        "viewer",
                        signaling_url=share_signaling_url,
                    )
                    or {}
                ).get("inviteCode", ""),
                "prompterInviteCode": (
                    host.build_room_share_payload(
                        room_name,
                        "prompter",
                        signaling_url=share_signaling_url,
                    )
                    or {}
                ).get("inviteCode", ""),
            }
            for room_name, role_map in host.get_room_tokens().items()
        ]
    }
    _print_multiplayer_join_hints(
        share_signaling_url,
        {str(room.get("name", "")): dict(room) for room in initial_payload["rooms"]},
    )

    if enable_ngrok:
        tunnel = NgrokTunnel(f"{bind_host}:{port}")
        public_https = await tunnel.start()
        if public_https:
            public_signaling_url = public_https + "/rpc"
            public_payload = {
                str(room_name): {
                    "viewerInviteCode": (
                        host.build_room_share_payload(
                            room_name,
                            "viewer",
                            signaling_url=public_signaling_url,
                        )
                        or {}
                    ).get("inviteCode", ""),
                    "prompterInviteCode": (
                        host.build_room_share_payload(
                            room_name,
                            "prompter",
                            signaling_url=public_signaling_url,
                        )
                        or {}
                    ).get("inviteCode", ""),
                }
                for room_name, role_map in host.get_room_tokens().items()
            }
            _print_multiplayer_join_hints(public_signaling_url, public_payload)
        else:
            logger.warning("ngrok helper failed; host is still running on local interface")

    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        await host.stop()
        if tunnel is not None:
            await tunnel.stop()
