#!/usr/bin/env python3
"""Smoke-test the poor-cli JSON-RPC server over stdio."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Sequence


def _send(proc: subprocess.Popen[bytes], message: dict) -> None:
    body = json.dumps(message).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("utf-8")
    assert proc.stdin is not None
    proc.stdin.write(header + body)
    proc.stdin.flush()


def _read_message(proc: subprocess.Popen[bytes]) -> dict:
    assert proc.stdout is not None

    header = b""
    while b"\r\n\r\n" not in header:
        chunk = proc.stdout.read(1)
        if not chunk:
            raise RuntimeError("Unexpected EOF while reading response headers")
        header += chunk

    header_text, _, body_prefix = header.partition(b"\r\n\r\n")
    content_length = 0
    for line in header_text.decode("utf-8").split("\r\n"):
        if line.lower().startswith("content-length:"):
            content_length = int(line.split(":", 1)[1].strip())
            break

    if content_length <= 0:
        raise RuntimeError("Missing or invalid Content-Length in response")

    body = body_prefix
    while len(body) < content_length:
        chunk = proc.stdout.read(content_length - len(body))
        if not chunk:
            raise RuntimeError("Unexpected EOF while reading response body")
        body += chunk

    return json.loads(body[:content_length].decode("utf-8"))


def run_smoke(command: Sequence[str], permission_mode: str = "prompt") -> None:
    proc = subprocess.Popen(
        list(command),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    try:
        _send(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"permissionMode": permission_mode},
            },
        )
        init_response = _read_message(proc)
        if init_response.get("id") != 1:
            raise RuntimeError(f"initialize response id mismatch: {init_response}")

        _send(proc, {"jsonrpc": "2.0", "id": 2, "method": "shutdown", "params": {}})
        shutdown_response = _read_message(proc)
        if shutdown_response.get("id") != 2:
            raise RuntimeError(f"shutdown response id mismatch: {shutdown_response}")
        if "error" in shutdown_response:
            raise RuntimeError(f"shutdown failed: {shutdown_response}")

        proc.wait(timeout=10)
        if proc.returncode not in (0, None):
            stderr_text = ""
            if proc.stderr is not None:
                stderr_text = proc.stderr.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"server exited with status {proc.returncode}: {stderr_text}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
        help="Server command to execute, for example: poor-cli-server --stdio",
    )
    parser.add_argument(
        "--permission-mode",
        default="prompt",
        help="Permission mode used for the initialize request",
    )
    args = parser.parse_args(argv)
    if not args.command:
        parser.error("A server command is required")

    run_smoke(args.command, permission_mode=args.permission_mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
