"""STDIO transport for JSON-RPC 2.0 using LSP-style Content-Length framing."""

import asyncio
import json
import sys
from typing import Optional

from ..exceptions import setup_logger
from .types import JsonRpcMessage

logger = setup_logger(__name__)


class StdioTransport:
    """Read/write JSON-RPC messages over stdin/stdout with Content-Length framing."""

    def __init__(self) -> None:
        self.logger = setup_logger("poor_cli.server.transport")

    async def read_message(self) -> Optional[JsonRpcMessage]:
        """Read a JSON-RPC message from stdin using Content-Length headers.

        Returns:
            Parsed message or None on EOF.
        """
        try:
            loop = asyncio.get_event_loop()
            stdin_reader = getattr(sys.stdin, "buffer", sys.stdin)

            header_buffer = b""
            header_delimiter = None
            while header_delimiter is None:
                chunk = await loop.run_in_executor(None, lambda: stdin_reader.read(1))
                if not chunk:
                    return None
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                header_buffer += chunk

                if b"\r\n\r\n" in header_buffer:
                    header_delimiter = b"\r\n\r\n"
                elif b"\n\n" in header_buffer:
                    header_delimiter = b"\n\n"

            header_text, body_prefix = header_buffer.split(header_delimiter, 1)
            header_text_decoded = header_text.decode("ascii", errors="replace")

            content_length = 0
            for raw_line in header_text_decoded.splitlines():
                line = raw_line.strip()
                if line.lower().startswith("content-length:"):
                    content_length = int(line.split(":", 1)[1].strip())
                    break

            if content_length <= 0:
                return None

            body = body_prefix
            while len(body) < content_length:
                remaining = content_length - len(body)
                chunk = await loop.run_in_executor(
                    None, lambda size=remaining: stdin_reader.read(size)
                )
                if not chunk:
                    return None
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                body += chunk

            body = body[:content_length]
            return JsonRpcMessage.from_json(body.decode("utf-8"))

        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Read error: {e}")
            return None

    async def write_message(self, message: JsonRpcMessage) -> None:
        """Write a JSON-RPC message to stdout using Content-Length headers."""
        try:
            body = message.to_json().encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")

            stdout_writer = getattr(sys.stdout, "buffer", None)
            if stdout_writer is not None:
                stdout_writer.write(header)
                stdout_writer.write(body)
                stdout_writer.flush()
            else:
                sys.stdout.write((header + body).decode("utf-8"))
                sys.stdout.flush()

        except Exception as e:
            self.logger.error(f"Write error: {e}")
