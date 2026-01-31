"""
PoorCLI JSON-RPC Server

This module provides a JSON-RPC 2.0 server for editor integrations.
It supports both stdio transport (for Neovim) and HTTP transport (for VSCode).
"""

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .core import PoorCLICore
from .exceptions import ConfigurationError, PoorCLIError, setup_logger

logger = setup_logger(__name__)


# =============================================================================
# JSON-RPC Message Types
# =============================================================================

@dataclass
class JsonRpcMessage:
    """JSON-RPC 2.0 message."""
    jsonrpc: str = "2.0"
    id: Optional[int] = None
    method: Optional[str] = None
    params: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary, excluding None values."""
        d = {"jsonrpc": self.jsonrpc}
        if self.id is not None:
            d["id"] = self.id
        if self.method is not None:
            d["method"] = self.method
        if self.params is not None:
            d["params"] = self.params
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        return d
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JsonRpcMessage":
        """Create from dictionary."""
        return cls(
            jsonrpc=data.get("jsonrpc", "2.0"),
            id=data.get("id"),
            method=data.get("method"),
            params=data.get("params"),
            result=data.get("result"),
            error=data.get("error")
        )
    
    @classmethod
    def from_json(cls, text: str) -> "JsonRpcMessage":
        """Parse from JSON string."""
        data = json.loads(text)
        return cls.from_dict(data)


class JsonRpcError:
    """JSON-RPC 2.0 error codes."""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    
    @classmethod
    def make_error(cls, code: int, message: str, data: Any = None) -> Dict[str, Any]:
        """Create an error object."""
        error = {"code": code, "message": message}
        if data is not None:
            error["data"] = data
        return error


# =============================================================================
# PoorCLI Server
# =============================================================================

class PoorCLIServer:
    """
    JSON-RPC server for PoorCLI.
    
    Provides editor integration via:
    - stdio transport (for Neovim)
    - HTTP transport (for VSCode and others)
    """
    
    def __init__(self):
        """Initialize the server."""
        self.core = PoorCLICore()
        self.handlers: Dict[str, Callable] = {}
        self.initialized = False
        self.logger = logging.getLogger("poor-cli-server")
        self._running = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        """Register JSON-RPC method handlers."""
        self.handlers = {
            "initialize": self.handle_initialize,
            "shutdown": self.handle_shutdown,
            "textDocument/completion": self.handle_completion,
            "poor-cli/chat": self.handle_chat,
            "poor-cli/inlineComplete": self.handle_inline_complete,
            "poor-cli/applyEdit": self.handle_apply_edit,
            "poor-cli/readFile": self.handle_read_file,
            "poor-cli/executeCommand": self.handle_execute_command,
            "poor-cli/getTools": self.handle_get_tools,
            "poor-cli/switchProvider": self.handle_switch_provider,
            "poor-cli/getProviderInfo": self.handle_get_provider_info,
            "poor-cli/clearHistory": self.handle_clear_history,
        }
    
    # =========================================================================
    # Handler Methods
    # =========================================================================
    
    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Initialize the server with provider configuration.
        
        Params:
            provider: Optional provider name
            model: Optional model name
            apiKey: Optional API key
        
        Returns:
            Server capabilities
        """
        try:
            await self.core.initialize(
                provider_name=params.get("provider"),
                model_name=params.get("model"),
                api_key=params.get("apiKey")
            )
            self.initialized = True
            
            return {
                "capabilities": {
                    "completionProvider": True,
                    "inlineCompletionProvider": True,
                    "chatProvider": True,
                    "fileOperations": True,
                    "providerInfo": self.core.get_provider_info()
                }
            }
        except ConfigurationError as e:
            raise Exception(f"Initialization failed: {e}")
    
    async def handle_shutdown(self, params: Dict[str, Any]) -> None:
        """Shutdown the server."""
        self.logger.info("Shutdown requested")
        self._running = False
        return None
    
    async def handle_completion(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle LSP-style text document completion."""
        # For now, redirect to inline complete
        return await self.handle_inline_complete(params)
    
    async def handle_chat(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle chat message.
        
        Params:
            message: The message to send
            contextFiles: Optional list of file paths for context
        
        Returns:
            content: Response text
            role: "assistant"
        """
        self._ensure_initialized()
        
        message = params.get("message", "")
        context_files = params.get("contextFiles")
        
        response_text = await self.core.send_message_sync(
            message=message,
            context_files=context_files
        )
        
        return {
            "content": response_text,
            "role": "assistant"
        }
    
    async def handle_inline_complete(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle inline code completion.
        
        Params:
            codeBefore: Code before cursor
            codeAfter: Code after cursor
            instruction: Optional instruction
            filePath: Current file path
            language: Programming language
        
        Returns:
            completion: Generated code
            isPartial: Whether this is a partial result
        """
        self._ensure_initialized()
        
        code_before = params.get("codeBefore", "")
        code_after = params.get("codeAfter", "")
        instruction = params.get("instruction", "")
        file_path = params.get("filePath", "")
        language = params.get("language", "")
        
        # Collect all chunks
        chunks = []
        async for chunk in self.core.inline_complete(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language
        ):
            chunks.append(chunk)
        
        return {
            "completion": "".join(chunks),
            "isPartial": False
        }
    
    async def handle_apply_edit(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply a code edit.
        
        Params:
            filePath: File to edit
            oldText: Text to replace
            newText: Replacement text
        
        Returns:
            success: Whether the edit succeeded
            message: Result message
        """
        self._ensure_initialized()
        
        file_path = params.get("filePath", "")
        old_text = params.get("oldText", "")
        new_text = params.get("newText", "")
        
        result = await self.core.apply_edit(
            file_path=file_path,
            old_text=old_text,
            new_text=new_text
        )
        
        success = not result.startswith("Error")
        
        return {
            "success": success,
            "message": result
        }
    
    async def handle_read_file(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read a file.
        
        Params:
            filePath: File to read
            startLine: Optional start line
            endLine: Optional end line
        
        Returns:
            content: File contents
        """
        self._ensure_initialized()
        
        file_path = params.get("filePath", "")
        start_line = params.get("startLine")
        end_line = params.get("endLine")
        
        content = await self.core.read_file(
            file_path=file_path,
            start_line=start_line,
            end_line=end_line
        )
        
        return {"content": content}
    
    async def handle_execute_command(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a shell command.
        
        Params:
            command: Command to execute
        
        Returns:
            output: Command output
            exitCode: Exit code (always 0 for now)
        """
        self._ensure_initialized()
        
        command = params.get("command", "")
        
        result = await self.core.execute_tool("bash", {"command": command})
        
        return {
            "output": result,
            "exitCode": 0
        }
    
    async def handle_get_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get available tools.
        
        Returns:
            tools: List of tool declarations
        """
        self._ensure_initialized()
        
        return {"tools": self.core.get_available_tools()}
    
    async def handle_switch_provider(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Switch AI provider.
        
        Params:
            provider: Provider name
            model: Optional model name
        
        Returns:
            success: Whether the switch succeeded
            provider: New provider info
        """
        self._ensure_initialized()
        
        provider = params.get("provider", "")
        model = params.get("model")
        
        await self.core.switch_provider(provider, model)
        
        return {
            "success": True,
            "provider": self.core.get_provider_info()
        }
    
    async def handle_get_provider_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Get current provider info.
        
        Returns:
            Provider info dict
        """
        self._ensure_initialized()
        return self.core.get_provider_info()
    
    async def handle_clear_history(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clear conversation history.
        
        Returns:
            success: Always true
        """
        self._ensure_initialized()
        await self.core.clear_history()
        return {"success": True}
    
    def _ensure_initialized(self) -> None:
        """Ensure the server is initialized."""
        if not self.initialized:
            raise Exception("Server not initialized. Call 'initialize' first.")
    
    # =========================================================================
    # Message Dispatch
    # =========================================================================
    
    async def dispatch(self, message: JsonRpcMessage) -> JsonRpcMessage:
        """
        Dispatch a JSON-RPC message to the appropriate handler.
        
        Args:
            message: The incoming message
        
        Returns:
            Response message
        """
        if not message.method:
            return JsonRpcMessage(
                id=message.id,
                error=JsonRpcError.make_error(
                    JsonRpcError.INVALID_REQUEST,
                    "Missing method"
                )
            )
        
        handler = self.handlers.get(message.method)
        if not handler:
            return JsonRpcMessage(
                id=message.id,
                error=JsonRpcError.make_error(
                    JsonRpcError.METHOD_NOT_FOUND,
                    f"Unknown method: {message.method}"
                )
            )
        
        try:
            result = await handler(message.params or {})
            return JsonRpcMessage(
                id=message.id,
                result=result
            )
        except Exception as e:
            self.logger.exception(f"Handler error for {message.method}")
            return JsonRpcMessage(
                id=message.id,
                error=JsonRpcError.make_error(
                    JsonRpcError.INTERNAL_ERROR,
                    str(e)
                )
            )
    
    # =========================================================================
    # STDIO Transport
    # =========================================================================
    
    async def read_message_stdio(self) -> Optional[JsonRpcMessage]:
        """
        Read a JSON-RPC message from stdin.
        
        Uses the LSP-style Content-Length header protocol.
        
        Returns:
            Parsed message or None on EOF.
        """
        try:
            # Read headers until empty line
            content_length = 0
            
            while True:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )
                
                if not line:
                    return None  # EOF
                
                line = line.strip()
                
                if not line:
                    break  # End of headers
                
                if line.startswith("Content-Length:"):
                    content_length = int(line.split(":")[1].strip())
            
            if content_length == 0:
                return None
            
            # Read body
            body = await asyncio.get_event_loop().run_in_executor(
                None, lambda: sys.stdin.read(content_length)
            )
            
            if not body:
                return None
            
            return JsonRpcMessage.from_json(body)
            
        except json.JSONDecodeError as e:
            self.logger.error(f"JSON parse error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Read error: {e}")
            return None
    
    async def write_message_stdio(self, message: JsonRpcMessage) -> None:
        """
        Write a JSON-RPC message to stdout.
        
        Uses the LSP-style Content-Length header protocol.
        
        Args:
            message: The message to write.
        """
        try:
            body = message.to_json()
            content = f"Content-Length: {len(body)}\r\n\r\n{body}"
            
            sys.stdout.write(content)
            sys.stdout.flush()
            
        except Exception as e:
            self.logger.error(f"Write error: {e}")
    
    async def run_stdio(self) -> None:
        """
        Run the server using stdio transport.
        
        Reads JSON-RPC messages from stdin and writes responses to stdout.
        """
        self.logger.info("Starting stdio server")
        self._running = True
        
        while self._running:
            try:
                message = await self.read_message_stdio()
                
                if message is None:
                    self.logger.info("EOF received, shutting down")
                    break
                
                response = await self.dispatch(message)
                
                # Only send response if there's an id (not a notification)
                if message.id is not None:
                    await self.write_message_stdio(response)
                    
            except Exception as e:
                self.logger.exception("Error in main loop")
        
        self.logger.info("Stdio server stopped")


# =============================================================================
# Streaming Server Extension
# =============================================================================

class StreamingJsonRpcServer(PoorCLIServer):
    """
    Extended server with streaming support.
    
    Overrides chat and inline complete to send streaming notifications.
    """
    
    async def handle_chat_streaming(self, params: Dict[str, Any], request_id: int) -> None:
        """
        Handle chat with streaming responses.
        
        Sends partial results as notifications with method "poor-cli/streamChunk".
        """
        self._ensure_initialized()
        
        message = params.get("message", "")
        context_files = params.get("contextFiles")
        
        async for chunk in self.core.send_message(
            message=message,
            context_files=context_files
        ):
            # Send streaming notification
            notification = JsonRpcMessage(
                method="poor-cli/streamChunk",
                params={
                    "requestId": request_id,
                    "chunk": chunk,
                    "done": False
                }
            )
            await self.write_message_stdio(notification)
        
        # Send final notification
        final = JsonRpcMessage(
            method="poor-cli/streamChunk",
            params={
                "requestId": request_id,
                "chunk": "",
                "done": True
            }
        )
        await self.write_message_stdio(final)


# =============================================================================
# HTTP Transport (for VSCode and others)
# =============================================================================

async def run_http(server: PoorCLIServer, host: str = "127.0.0.1", port: int = 9876) -> None:
    """
    Run the server using HTTP transport.
    
    Creates an HTTP server that accepts JSON-RPC requests.
    Also provides a WebSocket endpoint for streaming.
    
    Args:
        server: The PoorCLIServer instance
        host: Host to bind to
        port: Port to bind to
    """
    try:
        from aiohttp import web
    except ImportError:
        logger.error("aiohttp not installed. Run: pip install aiohttp")
        return
    
    async def handle_jsonrpc(request: web.Request) -> web.Response:
        """Handle POST /jsonrpc requests."""
        try:
            body = await request.text()
            message = JsonRpcMessage.from_json(body)
            response = await server.dispatch(message)
            return web.json_response(response.to_dict())
        except json.JSONDecodeError:
            return web.json_response(
                JsonRpcMessage(
                    error=JsonRpcError.make_error(
                        JsonRpcError.PARSE_ERROR,
                        "Invalid JSON"
                    )
                ).to_dict(),
                status=400
            )
    
    async def handle_health(request: web.Request) -> web.Response:
        """Handle GET /health requests."""
        return web.json_response({
            "status": "ok",
            "initialized": server.initialized,
            "provider": server.core.get_provider_info() if server.initialized else None
        })
    
    app = web.Application()
    app.router.add_post("/jsonrpc", handle_jsonrpc)
    app.router.add_get("/health", handle_health)
    
    runner = web.AppRunner(app)
    await runner.setup()
    
    site = web.TCPSite(runner, host, port)
    await site.start()
    
    logger.info(f"HTTP server running on http://{host}:{port}")
    
    # Keep running until interrupted
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        pass
    finally:
        await runner.cleanup()


# =============================================================================
# Main Entry Point
# =============================================================================

def main() -> None:
    """Main entry point for the server."""
    parser = argparse.ArgumentParser(
        description="PoorCLI JSON-RPC Server for editor integration"
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Use stdio transport (for Neovim)"
    )
    parser.add_argument(
        "--http",
        action="store_true",
        help="Use HTTP transport (for VSCode)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9876,
        help="Port for HTTP server (default: 9876)"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for HTTP server (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        stream=sys.stderr  # Log to stderr to keep stdout clean for JSON-RPC
    )
    
    server = PoorCLIServer()
    
    if args.stdio:
        asyncio.run(server.run_stdio())
    elif args.http:
        asyncio.run(run_http(server, args.host, args.port))
    else:
        # Default to stdio
        asyncio.run(server.run_stdio())


if __name__ == "__main__":
    main()
