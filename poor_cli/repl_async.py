"""
Async REPL interface for poor-cli with streaming support
"""

import os
import sys
import asyncio
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.live import Live
from rich import print as rprint
from google.generativeai.types import protos

from .gemini_client_async import GeminiClientAsync
from .tools_async import ToolRegistryAsync
from .config import get_config_manager, Config
from .history import HistoryManager
from .error_recovery import ErrorRecoveryManager
from .exceptions import (
    PoorCLIError,
    APIError,
    APIConnectionError,
    APITimeoutError,
    APIRateLimitError,
    ConfigurationError,
    setup_logger,
)

# Setup logger
logger = setup_logger(__name__)


class PoorCLIAsync:
    """Async REPL interface with streaming support"""

    def __init__(self):
        self.console = Console()
        self.client: Optional[GeminiClientAsync] = None
        self.tool_registry = ToolRegistryAsync()
        self.config_manager = get_config_manager()
        self.config: Config = self.config_manager.config
        self.history_manager: Optional[HistoryManager] = None
        self.error_recovery = ErrorRecoveryManager()
        self.running = False

    async def initialize(self):
        """Initialize the Gemini client and tools with proper error handling"""
        try:
            logger.info("Initializing poor-cli (async)...")

            # Initialize history manager
            if self.config.history.auto_save:
                self.history_manager = HistoryManager()
                self.history_manager.start_session(self.config.model.model_name)
                logger.info("History manager initialized")

            # Initialize Gemini client
            try:
                api_key = self.config_manager.get_api_key(self.config.model.provider)
                self.client = GeminiClientAsync(
                    api_key=api_key,
                    model_name=self.config.model.model_name
                )
                logger.info("Gemini client initialized successfully (async)")
            except ConfigurationError as e:
                self.console.print(
                    Panel(
                        f"[bold red]Configuration Error:[/bold red]\n{e}\n\n"
                        "[yellow]Please check:[/yellow]\n"
                        "1. GEMINI_API_KEY is set in your environment or .env file\n"
                        "2. Your API key is valid\n"
                        "3. Get a key from: https://makersuite.google.com/app/apikey",
                        title="⚠️  Configuration Error",
                        border_style="red",
                    )
                )
                logger.error(f"Configuration error: {e}")
                sys.exit(1)

            # Get tool declarations and initialize
            try:
                tool_declarations = self.tool_registry.get_tool_declarations()
                current_dir = os.getcwd()
                await self.client.set_tools(tool_declarations, current_dir=current_dir)
                logger.info(f"Initialized with {len(tool_declarations)} tools")
            except Exception as e:
                self.console.print(
                    f"[bold red]Error initializing tools:[/bold red] {e}",
                    style="red"
                )
                logger.error(f"Tool initialization error: {e}")
                sys.exit(1)

            # Display welcome message
            mascot = """[dim blue]        ___
      /     \\
     | () () |
      \\  ^  /
       |||||
      '-----'[/dim blue]
"""

            status_line = []
            if self.config.ui.enable_streaming:
                status_line.append("[green]streaming[/green]")
            if self.history_manager:
                status_line.append("[cyan]history[/cyan]")
            if self.config.ui.show_token_count:
                status_line.append("[yellow]tokens[/yellow]")

            status = " | ".join(status_line) if status_line else ""

            welcome_text = f"""{mascot}
[bold cyan]poor-cli[/bold cyan] [dim]v0.1.0[/dim] [dim blue](async)[/dim blue]
[dim]AI-powered CLI tool using {self.config.model.model_name}[/dim]
{status}

[bold]Commands:[/bold]
  [cyan]/help[/cyan]    - Show this help
  [cyan]/quit[/cyan]    - Exit the REPL
  [cyan]/clear[/cyan]   - Clear conversation history
  [cyan]/config[/cyan]  - Show configuration
  [cyan]/history[/cyan] - Show session history
"""

            self.console.print(
                Panel.fit(
                    welcome_text,
                    title="[bold cyan]Welcome[/bold cyan]",
                    border_style="cyan",
                    padding=(0, 1),
                )
            )
            logger.info("Initialization complete")

        except Exception as e:
            self.console.print(
                Panel(
                    f"[bold red]Unexpected Error:[/bold red]\n{type(e).__name__}: {e}\n\n"
                    "[yellow]Please check the logs for more details.[/yellow]",
                    title="⚠️  Initialization Failed",
                    border_style="red",
                )
            )
            logger.exception("Unexpected error during initialization")
            sys.exit(1)

    async def run(self):
        """Main async REPL loop"""
        await self.initialize()
        self.running = True

        while self.running:
            try:
                # Use asyncio-friendly input (run in thread to avoid blocking)
                user_input = await asyncio.to_thread(
                    Prompt.ask, "\n[bold cyan]You[/bold cyan]"
                )

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    await self.handle_command(user_input)
                    continue

                # Process AI request
                await self.process_request(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break

        # Cleanup
        if self.history_manager:
            self.history_manager.end_session()

        self.console.print("\n[cyan]Goodbye![/cyan]")

    async def handle_command(self, command: str):
        """Handle slash commands"""
        cmd = command.lower().strip()

        if cmd == "/quit" or cmd == "/exit":
            self.running = False

        elif cmd == "/help":
            self.console.print(
                Panel.fit(
                    "[bold]Available Commands:[/bold]\n\n"
                    "/help    - Show this help message\n"
                    "/quit    - Exit the REPL\n"
                    "/clear   - Clear conversation history\n"
                    "/config  - Show current configuration\n"
                    "/history - Show session statistics\n\n"
                    "[bold]Available Tools:[/bold]\n"
                    "- read_file: Read file contents\n"
                    "- write_file: Write to files (requires permission)\n"
                    "- edit_file: Edit files (requires permission)\n"
                    "- glob_files: Find files by pattern\n"
                    "- grep_files: Search in files\n"
                    "- bash: Execute bash commands (requires permission)\n\n"
                    "[dim]Note: File write/edit operations require permission.\n"
                    "Streaming mode is enabled for faster responses.[/dim]",
                    title="Help",
                    border_style="cyan",
                )
            )

        elif cmd == "/clear":
            await self.client.clear_history()
            if self.history_manager:
                self.history_manager.clear_current_session()
            self.console.print("[green]Conversation history cleared[/green]")

        elif cmd == "/config":
            config_display = self.config_manager.display_config()
            self.console.print(
                Panel(
                    config_display,
                    title="Current Configuration",
                    border_style="cyan",
                )
            )

        elif cmd == "/history":
            if self.history_manager:
                total_tokens = self.history_manager.get_total_tokens()
                msg_count = self.history_manager.get_message_count()
                session_id = self.history_manager.current_session.session_id

                self.console.print(
                    Panel(
                        f"[bold]Session ID:[/bold] {session_id}\n"
                        f"[bold]Messages:[/bold] {msg_count}\n"
                        f"[bold]Tokens (estimated):[/bold] {total_tokens}\n"
                        f"[bold]Model:[/bold] {self.config.model.model_name}",
                        title="Session History",
                        border_style="cyan",
                    )
                )
            else:
                self.console.print("[yellow]History tracking is disabled[/yellow]")

        else:
            self.console.print(f"[red]Unknown command: {command}[/red]")

    async def process_request(self, user_input: str):
        """Process user request with AI, streaming, and comprehensive error handling"""
        try:
            logger.info(f"Processing user request: {user_input[:100]}...")

            # Save user message to history
            if self.history_manager:
                self.history_manager.add_message("user", user_input)

            # Check if we should prune history
            if self.history_manager:
                current_tokens = self.history_manager.get_total_tokens()
                if current_tokens > self.config.history.max_token_limit:
                    pruned = self.history_manager.prune_history(
                        self.config.history.max_token_limit
                    )
                    if pruned > 0:
                        logger.info(f"Pruned {pruned} messages from history")

            # Use streaming if enabled
            if self.config.ui.enable_streaming:
                await self._process_request_streaming(user_input)
            else:
                await self._process_request_normal(user_input)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Request cancelled[/yellow]")
            logger.info("Request cancelled by user")
            raise

        except PoorCLIError as e:
            self.console.print(
                Panel(
                    f"[bold red]Error[/bold red]\n\n{e}",
                    title="⚠️  Error",
                    border_style="red",
                )
            )
            logger.error(f"Application error: {e}")

        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            self.console.print(
                Panel(
                    f"[bold red]Unexpected Error[/bold red]\n\n"
                    f"Type: {error_type}\n"
                    f"Message: {error_msg}\n\n"
                    "[yellow]Please check the logs for more details.[/yellow]",
                    title="⚠️  Unexpected Error",
                    border_style="red",
                )
            )
            logger.exception("Unexpected error processing request")

    async def _process_request_streaming(self, user_input: str):
        """Process request with streaming responses"""
        try:
            self.console.print("\n[bold green]Poor AI[/bold green]")

            accumulated_text = ""

            # Stream the response
            async for chunk in self.client.send_message_stream(user_input):
                try:
                    # Check if chunk has parts
                    if hasattr(chunk, 'candidates') and chunk.candidates:
                        part = chunk.candidates[0].content.parts[0]

                        # Handle function calls
                        if hasattr(part, "function_call") and part.function_call:
                            # For function calls, we need to handle them synchronously
                            # Collect all chunks first
                            full_response = chunk
                            tool_result_content = await self.execute_function_calls(full_response)

                            # Send tool results and continue
                            response = await self.client.send_message(tool_result_content)

                            # Display the final response
                            if hasattr(response.candidates[0].content.parts[0], "text"):
                                text = response.candidates[0].content.parts[0].text
                                accumulated_text += text
                                self.display_response(text)

                        # Handle text streaming
                        elif hasattr(part, "text"):
                            text = part.text
                            accumulated_text += text
                            self.console.print(text, end="")

                except Exception as e:
                    logger.error(f"Error processing chunk: {e}")
                    continue

            # Newline after streaming
            self.console.print()

            # Save assistant response to history
            if self.history_manager and accumulated_text:
                self.history_manager.add_message("model", accumulated_text)

        except APIRateLimitError as e:
            self._handle_api_error("Rate Limit Exceeded",
                                 "You've exceeded the API rate limit.", e)
        except APITimeoutError as e:
            self._handle_api_error("Request Timeout",
                                 "The request took too long to complete.", e)
        except APIConnectionError as e:
            self._handle_api_error("Connection Error",
                                 "Could not connect to the API.", e)
        except APIError as e:
            self._handle_api_error("API Error", str(e), e)

    async def _process_request_normal(self, user_input: str):
        """Process request with normal (non-streaming) responses"""
        try:
            # Show loading indicator
            with self.console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
                response = await self.client.send_message(user_input)

            # Handle function calls and responses
            try:
                while response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]

                    # Check if this is a function call
                    if hasattr(part, "function_call") and part.function_call:
                        tool_result_content = await self.execute_function_calls(response)

                        # Show loading indicator while processing tool results
                        with self.console.status(
                            "[cyan]Processing results...[/cyan]", spinner="dots"
                        ):
                            response = await self.client.send_message(tool_result_content)

                    # Check if this is text response
                    elif hasattr(part, "text"):
                        text = part.text
                        self.display_response(text)

                        # Save to history
                        if self.history_manager:
                            self.history_manager.add_message("model", text)

                        break
                    else:
                        break

                logger.info("Request processed successfully")

            except (IndexError, AttributeError) as e:
                self.console.print(
                    Panel(
                        "[bold red]Response Parse Error[/bold red]\n\n"
                        "Received an unexpected response format from the API.",
                        title="⚠️  Parse Error",
                        border_style="yellow",
                    )
                )
                logger.error(f"Error parsing API response: {e}", exc_info=True)

        except APIRateLimitError as e:
            self._handle_api_error("Rate Limit Exceeded",
                                 "You've exceeded the API rate limit.", e)
        except APITimeoutError as e:
            self._handle_api_error("Request Timeout",
                                 "The request took too long to complete.", e)
        except APIConnectionError as e:
            self._handle_api_error("Connection Error",
                                 "Could not connect to the API.", e)
        except APIError as e:
            self._handle_api_error("API Error", str(e), e)

    def _handle_api_error(self, title: str, message: str, exception: Exception):
        """Helper to display API errors consistently with recovery suggestions"""
        # Get recovery suggestions
        suggestions = self.error_recovery.get_suggestions(exception)
        suggestion_text = ""

        if suggestions:
            suggestion_text = "\n\n[bold cyan]Suggestions:[/bold cyan]\n"
            for i, sug in enumerate(suggestions[:3], 1):
                suggestion_text += f"{i}. {sug.title}: {sug.description}\n"
                if sug.commands:
                    suggestion_text += f"   Try: [dim]{sug.commands[0]}[/dim]\n"

        self.console.print(
            Panel(
                f"[bold red]{title}[/bold red]\n\n{message}{suggestion_text}",
                title=f"⚠️  {title}",
                border_style="yellow" if "Rate Limit" in title or "Timeout" in title else "red",
            )
        )
        logger.error(f"{title}: {exception}")

    async def request_permission(self, tool_name: str, tool_args: dict) -> bool:
        """Request user permission for file operations"""
        # Check config for permission requirements
        if tool_name == "bash" and not self.config.security.require_permission_for_bash:
            return True

        if tool_name in ["write_file", "edit_file"] and not self.config.security.require_permission_for_write:
            return True

        # Define which tools require permission
        file_operation_tools = {"write_file", "edit_file", "bash"}

        if tool_name not in file_operation_tools:
            return True

        # For bash commands, check if it's a safe read-only command
        if tool_name == "bash":
            command = tool_args.get("command", "").strip().lower()
            safe_commands = self.config.security.safe_commands

            if any(command.startswith(cmd) for cmd in safe_commands):
                return True

        # Build permission message
        if tool_name == "write_file":
            file_path = tool_args.get("file_path", "unknown")
            action_desc = f"[yellow]Write/Create file:[/yellow] {file_path}"
            details = f"[dim]This will create or overwrite the file.[/dim]"

        elif tool_name == "edit_file":
            file_path = tool_args.get("file_path", "unknown")
            action_desc = f"[yellow]Edit file:[/yellow] {file_path}"
            details = f"[dim]This will modify the file.[/dim]"

        elif tool_name == "bash":
            command = tool_args.get("command", "unknown")
            action_desc = f"[yellow]Execute bash command:[/yellow] {command}"
            details = f"[dim]This will run a shell command.[/dim]"
        else:
            return True

        # Display permission request
        self.console.print(
            Panel(
                f"{action_desc}\n{details}\n\n[bold]Allow this operation?[/bold]",
                title="⚠️  Permission Required",
                border_style="yellow",
            )
        )

        # Get user response (run in thread to avoid blocking)
        response = await asyncio.to_thread(
            Prompt.ask,
            "[bold]Choice[/bold]",
            choices=["y", "n", "yes", "no"],
            default="y"
        )

        return response.lower() in ["y", "yes"]

    async def execute_function_calls(self, response):
        """Execute function calls from Gemini response"""
        function_response_parts = []

        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args)

                self.console.print(f"\n[dim]→ Calling tool: {tool_name}[/dim]")

                # Request permission for file operations
                if not await self.request_permission(tool_name, tool_args):
                    result = f"Operation cancelled by user"
                    self.console.print("[yellow]Operation cancelled[/yellow]")
                else:
                    # Execute the tool asynchronously
                    result = await self.tool_registry.execute_tool(tool_name, tool_args)

                # Display tool output
                if result:
                    self.console.print(
                        Panel(
                            result[:1000] + ("..." if len(result) > 1000 else ""),
                            title=f"Tool Output: {tool_name}",
                            border_style="dim",
                            expand=False,
                        )
                    )

                # Prepare result for Gemini
                function_response_parts.append(
                    protos.Part(
                        function_response=protos.FunctionResponse(
                            name=tool_name, response={"result": result}
                        )
                    )
                )

        return protos.Content(role="user", parts=function_response_parts)

    def display_response(self, text: str):
        """Display AI response with markdown formatting"""
        self.console.print("\n[bold green]Poor AI[/bold green]")

        # Try to render as markdown if enabled
        if self.config.ui.markdown_rendering:
            try:
                md = Markdown(text)
                self.console.print(md)
            except Exception:
                self.console.print(text)
        else:
            self.console.print(text)


def main():
    """Entry point for async poor-cli"""
    try:
        repl = PoorCLIAsync()
        asyncio.run(repl.run())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
