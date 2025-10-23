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
from .repo_config import get_repo_config, RepoConfig
from .exceptions import (
    PoorCLIError,
    APIError,
    APIConnectionError,
    APITimeoutError,
    APIRateLimitError,
    ConfigurationError,
    setup_logger,
    enable_verbose_logging,
    disable_verbose_logging,
)
try:
    from .config import get_config_manager
    CONFIG_AVAILABLE = True
except ImportError:
    CONFIG_AVAILABLE = False

# Setup logger
logger = setup_logger(__name__)


class PoorCLI:
    """Main REPL interface"""

    def __init__(self):
        self.console = Console()
        self.client = None
        self.tool_registry = ToolRegistry()
        self.running = False
        self.verbose_mode = False
        self.repo_config: Optional[RepoConfig] = None

        # Initialize repo config for local history
        try:
            self.repo_config = get_repo_config()
            logger.info(f"Initialized repo config at {self.repo_config.config_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize repo config: {e}", exc_info=True)
            self.repo_config = None
            # Don't fail completely, just log the error

        # Check config for verbose setting
        if CONFIG_AVAILABLE:
            try:
                config_manager = get_config_manager()
                if config_manager.config.ui.verbose_logging:
                    self.verbose_mode = True
                    enable_verbose_logging()
            except Exception:
                pass  # Config not available or error loading

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

            # Start a new session for history tracking
            if self.repo_config:
                try:
                    self.repo_config.start_session(model="gemini-2.5-flash")
                    logger.info("Started new history session")
                except Exception as e:
                    logger.error(f"Failed to start history session: {e}", exc_info=True)
            else:
                logger.warning("No repo_config available, history will not be tracked")

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

        # End the session and save history
        if self.repo_config:
            try:
                self.repo_config.end_session()
                logger.info("Session ended and history saved")
            except Exception as e:
                logger.error(f"Failed to end session: {e}", exc_info=True)

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
                    "/help          - Show this help message\n"
                    "/quit          - Exit the REPL\n"
                    "/clear         - Clear conversation history\n"
                    "/verbose       - Toggle verbose logging (INFO/DEBUG messages)\n"
                    "/history       - Show chat history statistics\n"
                    "/history show  - Show recent messages from current session\n"
                    "/preferences   - Manage repo-level auto-approve settings\n\n"
                    "[bold]Available Tools:[/bold]\n"
                    "- read_file: Read file contents (no permission required)\n"
                    "- write_file: Write to files (requires permission)\n"
                    "- edit_file: Edit files (requires permission)\n"
                    "- glob_files: Find files by pattern (no permission required)\n"
                    "- grep_files: Search in files (no permission required)\n"
                    "- bash: Execute bash commands (requires permission for unsafe commands)\n\n"
                    "[dim]Note: Chat history is saved to .poor-cli/history.json\n"
                    "File write/edit operations and potentially unsafe bash commands\n"
                    "require your explicit permission before execution.\n"
                    "Safe read-only commands (pwd, ls, etc.) run automatically.[/dim]",
                    title="Help",
                    border_style="cyan",
                )
            )

        elif cmd == "/verbose":
            # Toggle verbose mode
            self.verbose_mode = not self.verbose_mode
            if self.verbose_mode:
                enable_verbose_logging()
                self.console.print("[green]Verbose logging enabled (INFO/DEBUG messages will be shown)[/green]")
            else:
                disable_verbose_logging()
                self.console.print("[green]Verbose logging disabled (only WARNING/ERROR messages will be shown)[/green]")

            # Save to config if available
            if CONFIG_AVAILABLE:
                try:
                    config_manager = get_config_manager()
                    config_manager.config.ui.verbose_logging = self.verbose_mode
                    config_manager.save()
                except Exception as e:
                    logger.debug(f"Could not save verbose setting to config: {e}")

        elif cmd == "/clear":
            # Reinitialize to clear history
            current_dir = os.getcwd()
            self.client.set_tools(
                self.tool_registry.get_tool_declarations(), current_dir=current_dir
            )
            if self.repo_config:
                self.repo_config.clear_history()
            self.console.print("[green]Conversation history cleared[/green]")

        elif cmd == "/history" or cmd.startswith("/history "):
            # Show chat history and statistics
            if not self.repo_config:
                self.console.print("[yellow]History tracking not available[/yellow]")
                logger.warning("History command called but repo_config is None")
                return

            try:
                # Parse optional count argument
                parts = cmd.split()
                show_messages = False
                message_count = 10  # default

                if len(parts) > 1:
                    if parts[1].lower() == "show":
                        show_messages = True
                        if len(parts) > 2:
                            try:
                                message_count = int(parts[2])
                            except ValueError:
                                pass

                session_stats = self.repo_config.get_session_stats()
                all_stats = self.repo_config.get_all_sessions_stats()

                # Build stats text
                if session_stats:
                    history_text = (
                        f"[bold]Current Session:[/bold]\n"
                        f"  Session ID: {session_stats['session_id']}\n"
                        f"  Started: {session_stats['started_at']}\n"
                        f"  Messages: {session_stats['message_count']}\n"
                        f"  Tokens (est): {session_stats['tokens_estimate']}\n"
                        f"  Model: {session_stats['model']}\n\n"
                    )
                else:
                    history_text = "[yellow]No active session[/yellow]\n\n"

                history_text += (
                    f"[bold]All Sessions:[/bold]\n"
                    f"  Total Sessions: {all_stats['total_sessions']}\n"
                    f"  Total Messages: {all_stats['total_messages']}\n"
                    f"  Total Tokens (est): {all_stats['total_tokens_estimate']}\n"
                    f"  Repo: {all_stats['repo_path']}\n\n"
                )

                # Show recent messages if requested
                if show_messages and self.repo_config.current_session:
                    recent_msgs = self.repo_config.get_recent_messages(message_count)
                    if recent_msgs:
                        history_text += f"[bold]Recent Messages (last {len(recent_msgs)}):[/bold]\n"
                        for msg in recent_msgs:
                            role_color = "cyan" if msg.role == "user" else "green"
                            role_name = "You" if msg.role == "user" else "AI"
                            content_preview = msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                            history_text += f"  [{role_color}]{role_name}:[/{role_color}] {content_preview}\n"
                        history_text += "\n"

                history_text += (
                    f"[dim]History file: {self.repo_config.history_file}[/dim]\n"
                    f"[dim]Use '/history show' to see recent messages[/dim]"
                )

                self.console.print(
                    Panel(
                        history_text,
                        title="Chat History",
                        border_style="cyan",
                    )
                )

            except Exception as e:
                self.console.print(f"[red]Error displaying history: {e}[/red]")
                logger.exception("Error in /history command")

        elif cmd == "/preferences":
            # Show and manage preferences
            if not self.repo_config:
                self.console.print("[yellow]Preferences not available[/yellow]")
                return

            prefs = self.repo_config.preferences
            pref_text = (
                f"[bold]Auto-Approve Settings:[/bold]\n"
                f"  Read operations:  {'✓ Enabled' if prefs.auto_approve_read else '✗ Disabled'}\n"
                f"  Write operations: {'✓ Enabled' if prefs.auto_approve_write else '✗ Disabled'}\n"
                f"  Edit operations:  {'✓ Enabled' if prefs.auto_approve_edit else '✗ Disabled'}\n"
                f"  Bash commands:    {'✓ Enabled' if prefs.auto_approve_bash else '✗ Disabled'}\n\n"
                f"[bold]Statistics:[/bold]\n"
                f"  Total Sessions: {prefs.total_sessions}\n"
                f"  Created: {prefs.created_at}\n"
                f"  Updated: {prefs.updated_at}\n\n"
                f"[dim]To toggle: /preferences <setting> (e.g., /preferences write)\n"
                f"Settings saved to: {self.repo_config.preferences_file}[/dim]"
            )

            self.console.print(
                Panel(
                    pref_text,
                    title="Repository Preferences",
                    border_style="cyan",
                )
            )

        elif cmd.startswith("/preferences "):
            # Toggle a specific preference
            if not self.repo_config:
                self.console.print("[yellow]Preferences not available[/yellow]")
                return

            parts = cmd.split()
            if len(parts) != 2:
                self.console.print("[red]Usage: /preferences <read|write|edit|bash>[/red]")
                return

            setting = parts[1].lower()
            pref_map = {
                "read": "auto_approve_read",
                "write": "auto_approve_write",
                "edit": "auto_approve_edit",
                "bash": "auto_approve_bash"
            }

            if setting not in pref_map:
                self.console.print(f"[red]Unknown setting: {setting}[/red]")
                self.console.print("[yellow]Available: read, write, edit, bash[/yellow]")
                return

            pref_key = pref_map[setting]
            current_value = self.repo_config.get_preference(pref_key)
            new_value = not current_value
            self.repo_config.update_preference(pref_key, new_value)

            status = "enabled" if new_value else "disabled"
            self.console.print(f"[green]Auto-approve for {setting} operations {status}[/green]")

        else:
            self.console.print(f"[red]Unknown command: {command}[/red]")

    def process_request(self, user_input: str):
        """Process user request with AI and comprehensive error handling"""
        try:
            logger.info(f"Processing user request: {user_input[:100]}...")

            # Log user message to history
            if self.repo_config:
                try:
                    self.repo_config.add_message("user", user_input)
                except Exception as e:
                    logger.error(f"Failed to log user message: {e}")

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
        """Request user permission for file operations with repo-level auto-approve"""
        # Define which tools require permission
        file_operation_tools = {"write_file", "edit_file", "bash"}

        if tool_name not in file_operation_tools:
            return True

        # Check repo-level auto-approve preferences
        if self.repo_config:
            operation_map = {
                "write_file": "write",
                "edit_file": "edit",
                "bash": "bash"
            }
            operation = operation_map.get(tool_name)
            if operation and self.repo_config.should_auto_approve(operation):
                logger.info(f"Auto-approved {operation} operation (repo preference)")
                return True

        # For bash commands, check if it's a safe read-only command
        if tool_name == "bash":
            command = tool_args.get("command", "").strip().lower()
            # Get safe commands from repo config if available
            if self.repo_config:
                safe_commands = self.repo_config.preferences.safe_bash_commands
            else:
                safe_commands = [
                    "pwd", "ls", "echo", "cat", "head", "tail",
                    "grep", "find", "which", "whoami", "date"
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

        # Log AI response to history
        if self.repo_config:
            try:
                self.repo_config.add_message("assistant", text)
            except Exception as e:
                logger.error(f"Failed to log assistant message: {e}")


def main():
    """Entry point for poor-cli"""
    repl = PoorCLI()
    repl.run()


if __name__ == "__main__":
    main()
