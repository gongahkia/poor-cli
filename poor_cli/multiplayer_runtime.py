"""Socket runtime for hosted multiplayer sessions."""

from __future__ import annotations

import argparse
import json
import socket
import socketserver
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Sequence

from .exceptions import ValidationError
from .multiplayer import MultiplayerStore


DEFAULT_MULTIPLAYER_HOST = "127.0.0.1"
DEFAULT_MULTIPLAYER_PORT = 8765


@dataclass(frozen=True)
class MultiplayerHostConfig:
    bind_host: str = DEFAULT_MULTIPLAYER_HOST
    port: int = DEFAULT_MULTIPLAYER_PORT
    display_name: str = "Host"
    repo_root: Path = Path.cwd()


class MultiplayerCommandRouter:
    def __init__(self, store: MultiplayerStore):
        self._store = store

    def handle(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        method = str(payload.get("method") or "").strip()
        params = payload.get("params")
        if not isinstance(params, dict):
            params = {}
        try:
            result = self._dispatch(method, params)
            return {"ok": True, "result": result}
        except Exception as exc:
            return {
                "ok": False,
                "error": {
                    "type": exc.__class__.__name__,
                    "message": str(exc),
                },
            }

    def _dispatch(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if method == "join":
            participant = self._store.join_session(str(params.get("displayName") or "Peer"))
            return {"participant": participant.to_dict(), "snapshot": self._snapshot()}
        if method == "snapshot":
            return self._snapshot()
        if method == "participants":
            return {
                "participants": [
                    participant.to_dict()
                    for participant in self._store.list_participants(
                        include_removed=bool(params.get("includeRemoved", False))
                    )
                ]
            }
        if method == "queue.enqueue":
            item = self._store.enqueue_prompt(
                str(params.get("authorId") or ""),
                str(params.get("prompt") or ""),
            )
            return {"item": item.to_dict(), "queue": self._queue()}
        if method == "queue.move":
            item = self._store.move_queue_item(
                str(params.get("actorId") or ""),
                str(params.get("itemId") or ""),
                str(params.get("direction") or ""),
            )
            return {"item": item.to_dict(), "queue": self._queue()}
        if method == "queue.update":
            item = self._store.update_queued_prompt(
                str(params.get("actorId") or ""),
                str(params.get("itemId") or ""),
                str(params.get("prompt") or ""),
            )
            return {"item": item.to_dict(), "queue": self._queue()}
        if method == "queue.cancel":
            item = self._store.cancel_queue_item(
                str(params.get("actorId") or ""),
                str(params.get("itemId") or ""),
            )
            return {"item": item.to_dict(), "queue": self._queue()}
        if method == "thread.create":
            metadata = params.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                raise ValidationError("metadata must be an object")
            thread = self._store.create_thread(
                str(params.get("creatorId") or ""),
                str(params.get("title") or ""),
                str(params.get("description") or ""),
                metadata=metadata,
            )
            return {"thread": thread.to_dict(), "threads": self._threads()}
        if method == "thread.event":
            metadata = params.get("metadata")
            if metadata is not None and not isinstance(metadata, dict):
                raise ValidationError("metadata must be an object")
            event = self._store.add_thread_event(
                str(params.get("threadId") or ""),
                str(params.get("authorId") or ""),
                str(params.get("eventType") or "comment"),
                str(params.get("content") or ""),
                metadata=metadata,
            )
            return {"event": event}
        raise ValidationError(f"unknown multiplayer method: {method}")

    def _snapshot(self) -> Dict[str, Any]:
        return {
            "participants": [
                participant.to_dict()
                for participant in self._store.list_participants()
            ],
            "queue": self._queue(),
            "threads": self._threads(),
            "approvalTemplates": [
                template.to_dict()
                for template in self._store.list_approval_templates()
            ],
        }

    def _queue(self) -> list[Dict[str, Any]]:
        return [item.to_dict() for item in self._store.list_queue(statuses=["queued", "running"])]

    def _threads(self) -> list[Dict[str, Any]]:
        return [thread.to_dict() for thread in self._store.list_threads()]


class _ThreadingTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self, server_address: tuple[str, int], handler_cls: type[socketserver.BaseRequestHandler], router: MultiplayerCommandRouter):
        self.router = router
        super().__init__(server_address, handler_cls)


class _MultiplayerRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        while True:
            raw = self.rfile.readline()
            if not raw:
                return
            try:
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("payload must be an object")
                response = self.server.router.handle(payload)
            except Exception as exc:
                response = {
                    "ok": False,
                    "error": {
                        "type": exc.__class__.__name__,
                        "message": str(exc),
                    },
                }
            self.wfile.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))


def serve_multiplayer_host(config: MultiplayerHostConfig) -> int:
    repo_root = config.repo_root.expanduser().resolve()
    store = MultiplayerStore(repo_root)
    host = store.host_session(config.display_name)
    router = MultiplayerCommandRouter(store)
    with _ThreadingTCPServer((config.bind_host, int(config.port)), _MultiplayerRequestHandler, router) as server:
        actual_host, actual_port = server.server_address
        print(
            f"poor-cli multiplayer host listening on {actual_host}:{actual_port} "
            f"as {host.display_name} ({host.participant_id})",
            flush=True,
        )
        try:
            server.serve_forever(poll_interval=0.25)
        except KeyboardInterrupt:
            return 0
    return 0


def send_multiplayer_command(
    host: str,
    port: int,
    method: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    timeout: float = 5.0,
) -> Dict[str, Any]:
    payload = {"method": method, "params": params or {}}
    with socket.create_connection((host, int(port)), timeout=timeout) as sock:
        with sock.makefile("rwb") as stream:
            stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
            stream.flush()
            raw = stream.readline()
    if not raw:
        raise RuntimeError("multiplayer host closed the connection")
    response = json.loads(raw.decode("utf-8"))
    if not isinstance(response, dict):
        raise RuntimeError("invalid multiplayer response")
    if not response.get("ok"):
        error = response.get("error") if isinstance(response.get("error"), dict) else {}
        raise RuntimeError(str(error.get("message") or "multiplayer command failed"))
    result = response.get("result")
    return result if isinstance(result, dict) else {}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="poor-cli multiplayer")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    host = sub.add_parser("host", help="Host a multiplayer session")
    host.add_argument("--bind", default=DEFAULT_MULTIPLAYER_HOST, help="Bind address")
    host.add_argument("--port", type=int, default=DEFAULT_MULTIPLAYER_PORT, help="TCP port")
    host.add_argument("--name", default="Host", help="Host display name")
    host.add_argument("--repo-root", default="", help="Repository root")

    join = sub.add_parser("join", help="Join a hosted multiplayer session")
    join.add_argument("--host", default=DEFAULT_MULTIPLAYER_HOST, help="Host address")
    join.add_argument("--port", type=int, default=DEFAULT_MULTIPLAYER_PORT, help="TCP port")
    join.add_argument("--name", default="Peer", help="Display name")
    join.add_argument("--json", action="store_true", help="Print raw JSON")

    attach = sub.add_parser("attach", help="Alias for join")
    attach.add_argument("--host", default=DEFAULT_MULTIPLAYER_HOST, help="Host address")
    attach.add_argument("--port", type=int, default=DEFAULT_MULTIPLAYER_PORT, help="TCP port")
    attach.add_argument("--name", default="Peer", help="Display name")
    attach.add_argument("--json", action="store_true", help="Print raw JSON")

    snapshot = sub.add_parser("snapshot", help="Fetch a hosted session snapshot")
    snapshot.add_argument("--host", default=DEFAULT_MULTIPLAYER_HOST, help="Host address")
    snapshot.add_argument("--port", type=int, default=DEFAULT_MULTIPLAYER_PORT, help="TCP port")
    snapshot.add_argument("--json", action="store_true", help="Print raw JSON")
    return parser


def run_multiplayer_mode(argv: Sequence[str]) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv))
    if args.subcommand == "host":
        repo_root = Path(args.repo_root).expanduser() if args.repo_root else Path.cwd()
        return serve_multiplayer_host(
            MultiplayerHostConfig(
                bind_host=str(args.bind),
                port=int(args.port),
                display_name=str(args.name),
                repo_root=repo_root,
            )
        )
    if args.subcommand in {"join", "attach"}:
        result = send_multiplayer_command(
            str(args.host),
            int(args.port),
            "join",
            {"displayName": str(args.name)},
        )
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            participant = result.get("participant") if isinstance(result.get("participant"), dict) else {}
            print(
                "joined multiplayer session as "
                f"{participant.get('displayName', args.name)} "
                f"({participant.get('participantId', 'unknown')})"
            )
        return 0
    if args.subcommand == "snapshot":
        result = send_multiplayer_command(str(args.host), int(args.port), "snapshot")
        if bool(args.json):
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            participants = result.get("participants") if isinstance(result.get("participants"), list) else []
            queue_items = result.get("queue") if isinstance(result.get("queue"), list) else []
            threads = result.get("threads") if isinstance(result.get("threads"), list) else []
            print(f"participants: {len(participants)}")
            print(f"queued prompts: {len(queue_items)}")
            print(f"task threads: {len(threads)}")
        return 0
    return 1
