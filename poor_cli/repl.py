"""
REPL interface for poor-cli
"""

import os
import sys
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich import print as rprint
from google.generativeai.types import protos

from .gemini_client import GeminiClient
from .tools import ToolRegistry
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


class PoorCLI:
    """Main REPL interface"""

    def __init__(self):
        self.console = Console()
        self.client = None
        self.tool_registry = ToolRegistry()
        self.running = False

    def initialize(self):
        """Initialize the Gemini client and tools with proper error handling"""
        try:
            logger.info("Initializing poor-cli...")

            # Initialize Gemini client
            try:
                self.client = GeminiClient()
                logger.info("Gemini client initialized successfully")
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
                self.client.set_tools(tool_declarations, current_dir=current_dir)
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

            welcome_text = f"""{mascot}
[bold cyan]poor-cli[/bold cyan] [dim]v0.1.0[/dim]
[dim]AI-powered CLI tool using Gemini[/dim]

[bold]Commands:[/bold]
  [cyan]/help[/cyan]  - Show this help
  [cyan]/quit[/cyan]  - Exit the REPL
  [cyan]/clear[/cyan] - Clear conversation history
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
            # Catch any unexpected errors during initialization
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

    def run(self):
        """Main REPL loop"""
        self.initialize()
        self.running = True

        while self.running:
            try:
                user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    self.handle_command(user_input)
                    continue

                # Process AI request
                self.process_request(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break

        self.console.print("\n[cyan]Goodbye![/cyan]")

    def handle_command(self, command: str):
        """Handle slash commands"""
        cmd = command.lower().strip()

        if cmd == "/quit" or cmd == "/exit":
            self.running = False

        elif cmd == "/help":
            self.console.print(
                Panel.fit(
                    "[bold]Available Commands:[/bold]\n\n"
                    "/help  - Show this help message\n"
                    "/quit  - Exit the REPL\n"
                    "/clear - Clear conversation history\n\n"
                    "[bold]Available Tools:[/bold]\n"
                    "- read_file: Read file contents (no permission required)\n"
                    "- write_file: Write to files (requires permission)\n"
                    "- edit_file: Edit files (requires permission)\n"
                    "- glob_files: Find files by pattern (no permission required)\n"
                    "- grep_files: Search in files (no permission required)\n"
                    "- bash: Execute bash commands (requires permission for unsafe commands)\n\n"
                    "[dim]Note: File write/edit operations and potentially unsafe\n"
                    "bash commands require your explicit permission before execution.\n"
                    "Safe read-only commands (pwd, ls, etc.) run automatically.[/dim]",
                    title="Help",
                    border_style="cyan",
                )
            )

        elif cmd == "/clear":
            # Reinitialize to clear history
            current_dir = os.getcwd()
            self.client.set_tools(
                self.tool_registry.get_tool_declarations(), current_dir=current_dir
            )
            self.console.print("[green]Conversation history cleared[/green]")

        else:
            self.console.print(f"[red]Unknown command: {command}[/red]")

    def process_request(self, user_input: str):
        """Process user request with AI and comprehensive error handling"""
        try:
            logger.info(f"Processing user request: {user_input[:100]}...")

            # Show loading indicator
            with self.console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
                try:
                    # Send message to Gemini
                    response = self.client.send_message(user_input)
                except APIRateLimitError as e:
                    self.console.print(
                        Panel(
                            "[bold red]Rate Limit Exceeded[/bold red]\n\n"
                            "You've exceeded the API rate limit. Please:\n"
                            "1. Wait a few minutes before trying again\n"
                            "2. Consider using a different API key\n"
                            "3. Check your quota at: https://makersuite.google.com/",
                            title="⚠️  Rate Limit",
                            border_style="yellow",
                        )
                    )
                    logger.warning(f"Rate limit exceeded: {e}")
                    return
                except APITimeoutError as e:
                    self.console.print(
                        Panel(
                            "[bold red]Request Timeout[/bold red]\n\n"
                            "The request took too long to complete.\n"
                            "Please try again or simplify your request.",
                            title="⚠️  Timeout",
                            border_style="yellow",
                        )
                    )
                    logger.warning(f"Request timeout: {e}")
                    return
                except APIConnectionError as e:
                    self.console.print(
                        Panel(
                            "[bold red]Connection Error[/bold red]\n\n"
                            "Could not connect to the Gemini API.\n"
                            "Please check your internet connection and try again.",
                            title="⚠️  Connection Error",
                            border_style="yellow",
                        )
                    )
                    logger.error(f"Connection error: {e}")
                    return
                except APIError as e:
                    self.console.print(
                        Panel(
                            f"[bold red]API Error[/bold red]\n\n{e}",
                            title="⚠️  API Error",
                            border_style="red",
                        )
                    )
                    logger.error(f"API error: {e}")
                    return

            # Handle function calls and responses
            try:
                while response.candidates[0].content.parts:
                    part = response.candidates[0].content.parts[0]

                    # Check if this is a function call
                    if hasattr(part, "function_call") and part.function_call:
                        tool_result_content = self.execute_function_calls(response)

                        # Show loading indicator while processing tool results
                        with self.console.status(
                            "[cyan]Processing results...[/cyan]", spinner="dots"
                        ):
                            try:
                                response = self.client.send_message(tool_result_content)
                            except APIError as e:
                                self.console.print(
                                    f"[bold red]Error processing tool results:[/bold red] {e}",
                                    style="red"
                                )
                                logger.error(f"Error processing tool results: {e}")
                                break

                    # Check if this is text response
                    elif hasattr(part, "text"):
                        self.display_response(part.text)
                        break
                    else:
                        break

                logger.info("Request processed successfully")

            except (IndexError, AttributeError) as e:
                self.console.print(
                    Panel(
                        "[bold red]Response Parse Error[/bold red]\n\n"
                        "Received an unexpected response format from the API.\n"
                        "This might be a temporary issue. Please try again.",
                        title="⚠️  Parse Error",
                        border_style="yellow",
                    )
                )
                logger.error(f"Error parsing API response: {e}", exc_info=True)

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Request cancelled[/yellow]")
            logger.info("Request cancelled by user")
            raise  # Re-raise to be handled by main loop

        except PoorCLIError as e:
            # Handle known application errors
            self.console.print(
                Panel(
                    f"[bold red]Error[/bold red]\n\n{e}",
                    title="⚠️  Error",
                    border_style="red",
                )
            )
            logger.error(f"Application error: {e}")

        except Exception as e:
            # Handle unexpected errors with detailed information
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

    def request_permission(self, tool_name: str, tool_args: dict) -> bool:
        """Request user permission for file operations"""
        # Define which tools require permission
        file_operation_tools = {"write_file", "edit_file", "bash"}

        if tool_name not in file_operation_tools:
            return True

        # For bash commands, check if it's a safe read-only command
        if tool_name == "bash":
            command = tool_args.get("command", "").strip().lower()
            # List of safe read-only commands that don't need permission
            safe_commands = [
                "pwd",
                "ls",
                "echo",
                "cat",
                "head",
                "tail",
                "grep",
                "find",
                "which",
                "whoami",
            ]
            # Check if command starts with a safe command
            if any(command.startswith(cmd) for cmd in safe_commands):
                return True

        # Build permission message based on tool type
        if tool_name == "write_file":
            file_path = tool_args.get("file_path", "unknown")
            action_desc = f"[yellow]Write/Create file:[/yellow] {file_path}"
            details = f"[dim]This will create or overwrite the file.[/dim]"

        elif tool_name == "edit_file":
            file_path = tool_args.get("file_path", "unknown")
            action_desc = f"[yellow]Edit file:[/yellow] {file_path}"
            if tool_args.get("old_text"):
                details = f"[dim]This will replace specific text in the file.[/dim]"
            else:
                start = tool_args.get("start_line", "?")
                end = tool_args.get("end_line", "?")
                details = f"[dim]This will modify lines {start}-{end}.[/dim]"

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

        # Get user response
        response = Prompt.ask(
            "[bold]Choice[/bold]", choices=["y", "n", "yes", "no"], default="y"
        )

        return response.lower() in ["y", "yes"]

    def execute_function_calls(self, response):
        """Execute function calls from Gemini response"""
        function_response_parts = []

        for part in response.candidates[0].content.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args)

                self.console.print(f"\n[dim]→ Calling tool: {tool_name}[/dim]")

                # Request permission for file operations
                if not self.request_permission(tool_name, tool_args):
                    result = f"Operation cancelled by user"
                    self.console.print("[yellow]Operation cancelled[/yellow]")
                else:
                    # Execute the tool
                    result = self.tool_registry.execute_tool(tool_name, tool_args)

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

                # Prepare result for Gemini using proper protos
                function_response_parts.append(
                    protos.Part(
                        function_response=protos.FunctionResponse(
                            name=tool_name, response={"result": result}
                        )
                    )
                )

        # Return as a Content object with role="user"
        return protos.Content(role="user", parts=function_response_parts)

    def display_response(self, text: str):
        """Display AI response with markdown formatting"""
        self.console.print("\n[bold green]Poor AI[/bold green]")

        # Try to render as markdown
        try:
            md = Markdown(text)
            self.console.print(md)
        except Exception:
            # Fallback to plain text
            self.console.print(text)


def main():
    """Entry point for poor-cli"""
    repl = PoorCLI()
    repl.run()


if __name__ == "__main__":
    main()
