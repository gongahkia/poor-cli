"""STDIO transport for JSON-RPC 2.0 using LSP-style Content-Length framing."""

import asyncio
import json
import sys
from typing import Optional

from ..exceptions import setup_logger
from .types import JsonRpcMessage

logger = setup_logger(__name__)


class StdioTransport:
    """Read/write JSON-RPC messages over stdin/stdout with Content-Length framing.

    Uses asyncio.StreamReader bound to stdin for header/body reads in one shot
    (readuntil / readexactly) instead of one-byte-at-a-time executor calls.
    """

    def __init__(self) -> None:
        self.logger = setup_logger("poor_cli.server.transport")
        self.last_error: Optional[Exception] = None
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._reader_lock = asyncio.Lock()
        self._writer_lock = asyncio.Lock()
        self._fallback_reader = False  # win32 or non-pipe stdin

    async def _ensure_reader(self) -> Optional[asyncio.StreamReader]:
        if self._reader is not None or self._fallback_reader:
            return self._reader
        loop = asyncio.get_event_loop()
        stdin_buf = getattr(sys.stdin, "buffer", sys.stdin)
        try:
            reader = asyncio.StreamReader(limit=8 * 1024 * 1024)  # 8MB line cap
            protocol = asyncio.StreamReaderProtocol(reader)
            await loop.connect_read_pipe(lambda: protocol, stdin_buf)
            self._reader = reader
            return reader
        except Exception as e:
            # windows pipes, tty, or closed stdin fall back to executor-based reads
            self.logger.warning(f"connect_read_pipe failed, falling back: {e}")
            self._fallback_reader = True
            return None

    async def _ensure_writer(self) -> Optional[asyncio.StreamWriter]:
        if self._writer is not None:
            return self._writer
        loop = asyncio.get_event_loop()
        stdout_buf = getattr(sys.stdout, "buffer", sys.stdout)
        try:
            transport, protocol = await loop.connect_write_pipe(
                asyncio.streams.FlowControlMixin, stdout_buf
            )
            self._writer = asyncio.StreamWriter(transport, protocol, None, loop)
            return self._writer
        except Exception as e:
            self.logger.warning(f"connect_write_pipe failed, using sync stdout: {e}")
            return None

    async def read_message(self) -> Optional[JsonRpcMessage]:
        """Read a JSON-RPC message from stdin using Content-Length headers."""
        self.last_error = None
        async with self._reader_lock:
            reader = await self._ensure_reader()
            if reader is not None:
                return await self._read_async(reader)
            return await self._read_fallback()

    async def _read_async(self, reader: asyncio.StreamReader) -> Optional[JsonRpcMessage]:
        try:
            try:
                header_bytes = await reader.readuntil(b"\r\n\r\n")
            except asyncio.IncompleteReadError as e:
                if not e.partial:
                    return None  # clean EOF
                # tolerate LF-only separator for non-spec clients
                if b"\n\n" in e.partial:
                    header_bytes = e.partial
                else:
                    self.last_error = EOFError("Incomplete JSON-RPC header")
                    return None
            except asyncio.LimitOverrunError as e:
                self.last_error = e
                self.logger.error(f"Header exceeds read buffer: {e}")
                return None

            header_text = header_bytes.decode("ascii", errors="replace")
            content_length = 0
            for raw_line in header_text.splitlines():
                line = raw_line.strip()
                if line.lower().startswith("content-length:"):
                    try:
                        content_length = int(line.split(":", 1)[1].strip())
                    except ValueError:
                        content_length = 0
                    break

            if content_length <= 0:
                self.last_error = ValueError("Missing or invalid Content-Length header")
                return None

            try:
                body = await reader.readexactly(content_length)
            except asyncio.IncompleteReadError:
                self.last_error = EOFError("Incomplete JSON-RPC body")
                return None

            return JsonRpcMessage.from_json(body.decode("utf-8"))

        except json.JSONDecodeError as e:
            self.last_error = e
            self.logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            self.last_error = e
            self.logger.error(f"Read error: {e}")
            return None

    async def _read_fallback(self) -> Optional[JsonRpcMessage]:
        # executor-based fallback for envs where connect_read_pipe fails
        try:
            loop = asyncio.get_event_loop()
            stdin_reader = getattr(sys.stdin, "buffer", sys.stdin)

            header_buffer = b""
            header_delimiter: Optional[bytes] = None
            while header_delimiter is None:
                # read in 4KB blocks instead of 1 byte; slice back once delim found
                chunk = await loop.run_in_executor(None, lambda: stdin_reader.read1(4096) if hasattr(stdin_reader, "read1") else stdin_reader.read(4096))
                if not chunk:
                    if header_buffer:
                        self.last_error = EOFError("Incomplete JSON-RPC header")
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
                self.last_error = ValueError("Missing or invalid Content-Length header")
                return None

            body = body_prefix
            while len(body) < content_length:
                remaining = content_length - len(body)
                chunk = await loop.run_in_executor(
                    None, lambda size=remaining: stdin_reader.read(size)
                )
                if not chunk:
                    self.last_error = EOFError("Incomplete JSON-RPC body")
                    return None
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                body += chunk

            body = body[:content_length]
            return JsonRpcMessage.from_json(body.decode("utf-8"))

        except json.JSONDecodeError as e:
            self.last_error = e
            self.logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            self.last_error = e
            self.logger.error(f"Read error (fallback): {e}")
            return None

    async def write_message(self, message: JsonRpcMessage) -> None:
        """Write a JSON-RPC message to stdout using Content-Length headers."""
        try:
            body = message.to_json().encode("utf-8")
            header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")

            async with self._writer_lock:
                writer = await self._ensure_writer()
                if writer is not None:
                    writer.write(header)
                    writer.write(body)
                    try:
                        await writer.drain()
                    except (ConnectionResetError, BrokenPipeError):
                        pass
                    return

                # fallback: sync write
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
