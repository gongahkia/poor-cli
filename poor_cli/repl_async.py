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

from .providers.provider_factory import ProviderFactory
from .providers.base import BaseProvider, ProviderResponse
from .tools_async import ToolRegistryAsync
from .enhanced_tools import EnhancedToolRegistry
from .config import get_config_manager, Config
from .history import HistoryManager
from .repo_config import get_repo_config, RepoConfig
from .error_recovery import ErrorRecoveryManager
from .checkpoint import CheckpointManager
from .checkpoint_display import CheckpointDisplay
from .diff_preview import DiffPreview
from .plan_executor import PlanExecutor
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

# Setup logger
logger = setup_logger(__name__)


class PoorCLIAsync:
    """Async REPL interface with streaming support and multi-provider support"""

    def __init__(self):
        self.console = Console()
        self.provider: Optional[BaseProvider] = None
        self.config_manager = get_config_manager()
        self.config: Config = self.config_manager.config
        self.history_manager: Optional[HistoryManager] = None
        self.repo_config: Optional[RepoConfig] = None  # For local JSON history
        self.error_recovery = ErrorRecoveryManager()
        self.running = False
        self.verbose_mode = self.config.ui.verbose_logging

        # Initialize checkpoint system
        try:
            self.checkpoint_manager = CheckpointManager()
            self.checkpoint_display = CheckpointDisplay(console=self.console)
            logger.info("Initialized checkpoint system")
        except Exception as e:
            logger.error(f"Failed to initialize checkpoint system: {e}", exc_info=True)
            self.checkpoint_manager = None
            self.checkpoint_display = None

        # Initialize diff preview
        self.diff_preview = DiffPreview(console=self.console)

        # Initialize enhanced tool registry
        self.tool_registry = EnhancedToolRegistry(
            config=self.config,
            checkpoint_manager=self.checkpoint_manager,
            diff_preview=self.diff_preview
        )

        # Initialize plan executor
        self.plan_executor = PlanExecutor(
            console=self.console,
            checkpoint_manager=self.checkpoint_manager,
            diff_preview=self.diff_preview
        )

        # Initialize repo config for local history
        try:
            self.repo_config = get_repo_config()
            logger.info(f"Initialized repo config at {self.repo_config.config_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize repo config: {e}", exc_info=True)
            self.repo_config = None

        # Enable verbose logging if set in config
        if self.verbose_mode:
            enable_verbose_logging()

    async def initialize(self):
        """Initialize the AI provider and tools with proper error handling"""
        try:
            logger.info("Initializing poor-cli (async)...")

            # Initialize history manager
            if self.config.history.auto_save:
                self.history_manager = HistoryManager()
                self.history_manager.start_session(self.config.model.model_name)
                logger.info("History manager initialized")

            # Start repo config session for local JSON history
            if self.repo_config:
                try:
                    self.repo_config.start_session(model=self.config.model.model_name)
                    logger.info("Started repo config history session")
                except Exception as e:
                    logger.error(f"Failed to start repo config session: {e}")

            # Initialize AI provider
            await self._initialize_provider()

            # Get tool declarations and initialize provider with tools
            try:
                tool_declarations = self.tool_registry.get_tool_declarations()
                current_dir = os.getcwd()

                # Build system instruction
                system_instruction = self._build_system_instruction(current_dir)

                # Initialize provider with tools
                await self.provider.initialize(
                    tools=tool_declarations,
                    system_instruction=system_instruction
                )
                logger.info(f"Initialized with {len(tool_declarations)} tools")

                # Restore previous conversation history if enabled
                if self.config.history.restore_on_startup:
                    await self._restore_conversation_history()

            except Exception as e:
                self.console.print(
                    f"[bold red]Error initializing tools:[/bold red] {e}",
                    style="red"
                )
                logger.error(f"Tool initialization error: {e}")
                sys.exit(1)

            # Display welcome message
            self._display_welcome()
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

    async def _initialize_provider(self):
        """Initialize the AI provider using factory"""
        try:
            # Get API key for provider
            api_key = self.config_manager.get_api_key(self.config.model.provider)

            if not api_key and self.config.model.provider != "ollama":
                self.console.print(
                    Panel(
                        f"[bold red]API Key Not Found:[/bold red]\n\n"
                        f"No API key found for provider: {self.config.model.provider}\n\n"
                        f"[yellow]Please set the environment variable:[/yellow]\n"
                        f"{self.config.model.providers[self.config.model.provider].api_key_env_var}\n\n"
                        f"Or add it to your .env file.",
                        title="⚠️  Configuration Error",
                        border_style="red",
                    )
                )
                logger.error(f"No API key for provider: {self.config.model.provider}")
                sys.exit(1)

            # Create provider
            logger.info(f"Creating {self.config.model.provider} provider...")

            # Get provider config for additional settings
            provider_config = self.config_manager.get_provider_config(self.config.model.provider)
            extra_kwargs = {}

            if provider_config and provider_config.base_url:
                extra_kwargs["base_url"] = provider_config.base_url

            self.provider = ProviderFactory.create(
                provider_name=self.config.model.provider,
                api_key=api_key or "",  # Ollama doesn't need API key
                model_name=self.config.model.model_name,
                **extra_kwargs
            )

            logger.info(f"Provider {self.config.model.provider} initialized successfully")

        except ConfigurationError as e:
            self.console.print(
                Panel(
                    f"[bold red]Configuration Error:[/bold red]\n{e}\n\n"
                    f"[yellow]Provider:[/yellow] {self.config.model.provider}\n"
                    f"[yellow]Model:[/yellow] {self.config.model.model_name}",
                    title="⚠️  Configuration Error",
                    border_style="red",
                )
            )
            logger.error(f"Configuration error: {e}")
            sys.exit(1)

    def _build_system_instruction(self, current_dir: str) -> str:
        """Build system instruction for the AI"""
        return f"""You are an AI assistant with TOOL CALLING capabilities. You have been given tools to perform file operations and system commands.

CRITICAL: When a user asks you to write/create a file, you MUST immediately call the write_file tool. DO NOT just show the code to the user. DO NOT say "write this to a file". Actually call the tool.

CURRENT WORKING DIRECTORY: {current_dir}

MANDATORY TOOL USAGE RULES:
1. File creation/writing: IMMEDIATELY call write_file(file_path, content)
2. File editing: IMMEDIATELY call edit_file(file_path, old_text, new_text)
3. File reading: IMMEDIATELY call read_file(file_path)
4. NEVER respond with just code snippets when asked to create a file
5. NEVER say "write this to a file" - YOU must call the tool yourself

Your available tools:
- write_file(file_path, content): Creates or overwrites a file
- edit_file(file_path, old_text, new_text): Edits existing files
- read_file(file_path): Reads file contents
- glob_files(pattern): Find files matching pattern
- grep_files(pattern): Search for text in files
- bash(command): Execute shell commands

FILE PATH RULES:
- ALWAYS use ABSOLUTE paths: {current_dir}/filename
- User says "create test.py" → use path: {current_dir}/test.py
- User says "create src/main.py" → use path: {current_dir}/src/main.py

IMPORTANT: Only call write_file if the user:
1. Explicitly asks to "create", "write", "save" a file, OR
2. Confirms they want to save code after you show it

If the user just asks for a solution/code without mentioning a file, show the code first and ask if they want it saved."""

    def _display_welcome(self):
        """Display welcome message"""
        mascot = """[dim blue]        ___
      /     \\
     | () () |
      \\  ^  /
       |||||
      '-----'[/dim blue]
"""

        status_line = []
        status_line.append(f"[magenta]{self.config.model.provider}[/magenta]")
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
  [cyan]/help[/cyan]         - Show all commands
  [cyan]/sessions[/cyan]     - View previous sessions
  [cyan]/new-session[/cyan]  - Start fresh conversation
  [cyan]/provider[/cyan]     - Show current provider
  [cyan]/switch[/cyan]       - Switch AI provider

[dim]Tip: History automatically persists across sessions in .poor-cli/[/dim]
"""

        self.console.print(
            Panel.fit(
                welcome_text,
                title="[bold cyan]Welcome[/bold cyan]",
                border_style="cyan",
                padding=(0, 1),
            )
        )

    async def _switch_provider(self):
        """Switch to a different AI provider"""
        # Get list of available providers
        available_providers = ProviderFactory.list_providers()

        if not available_providers:
            self.console.print("[red]No providers available[/red]")
            return

        # Display available providers
        self.console.print("\n[bold]Available Providers:[/bold]")
        provider_list = list(available_providers.keys())

        for i, provider_name in enumerate(provider_list, 1):
            current = " [green](current)[/green]" if provider_name == self.config.model.provider else ""
            prov_config = self.config.model.providers.get(provider_name)
            default_model = prov_config.default_model if prov_config else "N/A"
            self.console.print(f"  {i}. {provider_name} - {default_model}{current}")

        # Get user choice
        try:
            choice = await asyncio.to_thread(
                Prompt.ask,
                "\n[bold]Select provider[/bold]",
                choices=[str(i) for i in range(1, len(provider_list) + 1)] + ["c"],
                default="c"
            )

            if choice == "c":
                self.console.print("[yellow]Cancelled[/yellow]")
                return

            selected_provider = provider_list[int(choice) - 1]

            # Get model name
            prov_config = self.config.model.providers.get(selected_provider)
            default_model = prov_config.default_model if prov_config else ""

            model_name = await asyncio.to_thread(
                Prompt.ask,
                f"\n[bold]Model name[/bold]",
                default=default_model
            )

            # Update config
            self.config.model.provider = selected_provider
            self.config.model.model_name = model_name
            self.config_manager.save()

            # Reinitialize provider
            self.console.print(f"\n[cyan]Switching to {selected_provider} ({model_name})...[/cyan]")

            await self._initialize_provider()

            # Reinitialize with tools
            tool_declarations = self.tool_registry.get_tool_declarations()
            current_dir = os.getcwd()
            system_instruction = self._build_system_instruction(current_dir)

            await self.provider.initialize(
                tools=tool_declarations,
                system_instruction=system_instruction
            )

            self.console.print(f"[green]✓ Switched to {selected_provider}[/green]")

        except Exception as e:
            self.console.print(f"[red]Error switching provider: {e}[/red]")
            logger.error(f"Provider switch error: {e}", exc_info=True)

    async def _restore_conversation_history(self):
        """Restore conversation history from previous session"""
        try:
            if not self.repo_config:
                logger.debug("No repo config, skipping history restoration")
                return

            # Get recent messages from repo config
            max_messages = self.config.history.max_messages_to_restore
            recent_messages = self.repo_config.get_recent_messages(max_messages)

            if not recent_messages:
                logger.debug("No previous messages to restore")
                return

            # Convert messages to provider format and send them
            restored_count = 0
            provider_name = self.config.model.provider.lower()

            self.console.print(f"[dim]Restoring {len(recent_messages)} messages from previous session...[/dim]")

            for msg in recent_messages:
                try:
                    # Format message for provider
                    if provider_name == "gemini":
                        # Gemini needs to add to internal history differently
                        # We'll use the raw API to add to chat history
                        if hasattr(self.provider, 'chat') and hasattr(self.provider.chat, 'history'):
                            # Add to Gemini's internal history
                            role = "user" if msg.role == "user" else "model"
                            # Note: This is a workaround - ideally providers should support history injection
                            pass  # Gemini's history is managed internally through send_message

                    elif provider_name == "openai":
                        # OpenAI stores messages as list
                        if hasattr(self.provider, 'messages'):
                            role_map = {"user": "user", "assistant": "assistant", "model": "assistant"}
                            self.provider.messages.append({
                                "role": role_map.get(msg.role, msg.role),
                                "content": msg.content
                            })
                            restored_count += 1

                    elif provider_name in ["anthropic", "claude"]:
                        # Anthropic stores messages as list
                        if hasattr(self.provider, 'messages'):
                            role_map = {"user": "user", "assistant": "assistant", "model": "assistant"}
                            self.provider.messages.append({
                                "role": role_map.get(msg.role, msg.role),
                                "content": msg.content
                            })
                            restored_count += 1

                    elif provider_name == "ollama":
                        # Ollama stores messages as list (OpenAI-compatible)
                        if hasattr(self.provider, 'messages'):
                            role_map = {"user": "user", "assistant": "assistant", "model": "assistant"}
                            self.provider.messages.append({
                                "role": role_map.get(msg.role, msg.role),
                                "content": msg.content
                            })
                            restored_count += 1

                except Exception as e:
                    logger.warning(f"Failed to restore message: {e}")
                    continue

            if restored_count > 0:
                self.console.print(f"[dim green]✓ Restored {restored_count} messages from previous session[/dim green]")
                logger.info(f"Restored {restored_count} messages to provider history")
            else:
                logger.debug("No messages were restored to provider")

        except Exception as e:
            logger.error(f"Error restoring conversation history: {e}", exc_info=True)
            self.console.print(f"[dim yellow]⚠ Could not restore previous session: {e}[/dim yellow]")

    async def _list_sessions(self):
        """List all previous sessions from history database"""
        try:
            if not self.history_manager:
                self.console.print("[yellow]History tracking not enabled[/yellow]")
                return

            sessions = self.history_manager.list_sessions(limit=10)

            if not sessions:
                self.console.print("[yellow]No previous sessions found[/yellow]")
                return

            # Display sessions
            from datetime import datetime
            session_text = "[bold]Recent Sessions:[/bold]\n\n"

            for session_id, started_at, message_count in sessions:
                # Parse and format date
                try:
                    dt = datetime.fromisoformat(started_at)
                    date_str = dt.strftime("%Y-%m-%d %H:%M")
                except:
                    date_str = started_at

                session_text += f"[cyan]{session_id}[/cyan] - {date_str}\n"
                session_text += f"  Messages: {message_count}\n\n"

            self.console.print(Panel(session_text.strip(), title="Session History", border_style="cyan"))

        except Exception as e:
            self.console.print(f"[red]Error listing sessions: {e}[/red]")
            logger.error(f"Error listing sessions: {e}", exc_info=True)

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

        # End repo config session and save history
        if self.repo_config:
            try:
                self.repo_config.end_session()
                logger.info("Repo config session ended and history saved")
            except Exception as e:
                logger.error(f"Failed to end repo config session: {e}")

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
                    "[cyan]Session Management:[/cyan]\n"
                    "/help          - Show this help message\n"
                    "/quit          - Exit the REPL\n"
                    "/clear         - Clear current conversation\n"
                    "/history [N]   - Show recent messages (default: 10)\n"
                    "/sessions      - List all previous sessions\n"
                    "/new-session   - Start fresh (clear history)\n\n"
                    "[cyan]Checkpoints & Undo:[/cyan]\n"
                    "/checkpoints   - List all checkpoints\n"
                    "/checkpoint    - Create manual checkpoint\n"
                    "/rewind [ID]   - Restore checkpoint (ID or 'last')\n"
                    "/diff <f1> <f2> - Compare two files\n\n"
                    "[cyan]Provider Management:[/cyan]\n"
                    "/provider      - Show current provider info\n"
                    "/switch        - Switch AI provider\n\n"
                    "[cyan]Configuration:[/cyan]\n"
                    "/config        - Show current configuration\n"
                    "/verbose       - Toggle verbose logging\n"
                    "/plan-mode     - Toggle plan mode\n\n"
                    "[bold]Available Tools:[/bold]\n"
                    "- read_file: Read file contents\n"
                    "- write_file: Write to files (automatic checkpoint)\n"
                    "- edit_file: Edit files (automatic checkpoint)\n"
                    "- glob_files: Find files by pattern\n"
                    "- grep_files: Search in files\n"
                    "- bash: Execute bash commands (requires permission)\n\n"
                    "[dim]Note: Checkpoints are stored in .poor-cli/checkpoints/\n"
                    "Plan mode shows previews before executing changes.\n"
                    "Press Esc twice to restore the last checkpoint quickly.[/dim]",
                    title="Help",
                    border_style="cyan",
                )
            )

        elif cmd == "/clear":
            await self.provider.clear_history()
            if self.history_manager:
                self.history_manager.clear_current_session()
            self.console.print("[green]Conversation history cleared[/green]")

        elif cmd == "/provider":
            # Show current provider info
            caps = self.provider.get_capabilities()
            provider_info = f"""[bold]Current Provider:[/bold] {self.config.model.provider}
[bold]Model:[/bold] {self.config.model.model_name}

[bold]Capabilities:[/bold]
  Streaming: {'✓' if caps.supports_streaming else '✗'}
  Function Calling: {'✓' if caps.supports_function_calling else '✗'}
  Vision: {'✓' if caps.supports_vision else '✗'}
  Max Context: {caps.max_context_tokens:,} tokens
"""
            self.console.print(Panel(provider_info, title="Provider Info", border_style="cyan"))

        elif cmd == "/switch":
            # Switch provider
            await self._switch_provider()

        elif cmd == "/sessions":
            # List all previous sessions
            await self._list_sessions()

        elif cmd == "/new-session":
            # Start a completely new session (clear history)
            await self.provider.clear_history()
            if self.history_manager:
                self.history_manager.end_session()
                self.history_manager.start_session(self.config.model.model_name)
            if self.repo_config:
                self.repo_config.end_session()
                self.repo_config.start_session(model=self.config.model.model_name)
            self.console.print("[green]✓ Started new session (previous history cleared)[/green]")

        elif cmd == "/config":
            config_display = self.config_manager.display_config()
            self.console.print(
                Panel(
                    config_display,
                    title="Current Configuration",
                    border_style="cyan",
                )
            )

        elif cmd == "/history" or cmd.startswith("/history "):
            # Show recent messages from chat history
            if not self.repo_config:
                self.console.print("[yellow]History tracking not available[/yellow]")
                logger.warning("History command called but repo_config is None")
                return

            try:
                # Parse optional count argument
                parts = cmd.split()
                message_count = 10  # default

                if len(parts) > 1:
                    try:
                        message_count = int(parts[1])
                    except ValueError:
                        self.console.print(f"[yellow]Invalid number: {parts[1]}. Using default (10)[/yellow]")

                # Get recent messages
                if not self.repo_config.current_session:
                    self.console.print("[yellow]No active session[/yellow]")
                    return

                recent_msgs = self.repo_config.get_recent_messages(message_count)

                if not recent_msgs:
                    self.console.print("[yellow]No messages in current session[/yellow]")
                    return

                # Display messages
                history_text = ""
                for msg in recent_msgs:
                    role_color = "cyan" if msg.role == "user" else "green"
                    role_name = "You" if msg.role == "user" else "AI"
                    history_text += f"[{role_color}]{role_name}:[/{role_color}] {msg.content}\n\n"

                self.console.print(
                    Panel(
                        history_text.strip(),
                        title=f"Chat History (last {len(recent_msgs)} messages)",
                        border_style="cyan",
                    )
                )

            except Exception as e:
                self.console.print(f"[red]Error displaying history: {e}[/red]")
                logger.exception("Error in /history command")

        elif cmd == "/verbose":
            # Toggle verbose mode
            self.verbose_mode = not self.verbose_mode
            if self.verbose_mode:
                enable_verbose_logging()
                self.console.print("[green]Verbose logging enabled (INFO/DEBUG messages will be shown)[/green]")
            else:
                disable_verbose_logging()
                self.console.print("[green]Verbose logging disabled (only WARNING/ERROR messages will be shown)[/green]")

            # Save to config
            self.config.ui.verbose_logging = self.verbose_mode
            self.config_manager.save()

        elif cmd == "/plan-mode":
            # Toggle plan mode
            self.config.plan_mode.enabled = not self.config.plan_mode.enabled
            if self.config.plan_mode.enabled:
                self.console.print("[green]Plan mode enabled (preview before execution)[/green]")
            else:
                self.console.print("[yellow]Plan mode disabled (direct execution)[/yellow]")
            self.config_manager.save()

        elif cmd == "/checkpoints":
            # List all checkpoints
            if not self.checkpoint_manager or not self.checkpoint_display:
                self.console.print("[red]Checkpoint system not available[/red]")
                return

            checkpoints = self.checkpoint_manager.list_checkpoints(limit=20)
            self.checkpoint_display.display_checkpoint_list(checkpoints, show_details=True)
            self.checkpoint_display.display_storage_info(self.checkpoint_manager)

        elif cmd == "/checkpoint":
            # Create manual checkpoint
            if not self.checkpoint_manager or not self.checkpoint_display:
                self.console.print("[red]Checkpoint system not available[/red]")
                return

            # Get files in current directory
            from pathlib import Path
            current_files = list(Path.cwd().rglob("*.py"))[:10]  # First 10 Python files
            file_paths = [str(f) for f in current_files if f.is_file()]

            if not file_paths:
                self.console.print("[yellow]No files found to checkpoint[/yellow]")
                return

            # Create checkpoint
            try:
                checkpoint = self.checkpoint_manager.create_checkpoint(
                    file_paths=file_paths,
                    description="Manual checkpoint",
                    operation_type="manual"
                )
                self.checkpoint_display.display_checkpoint_created(checkpoint)
            except Exception as e:
                self.console.print(f"[red]Failed to create checkpoint: {e}[/red]")

        elif cmd.startswith("/rewind"):
            # Restore checkpoint
            if not self.checkpoint_manager or not self.checkpoint_display:
                self.console.print("[red]Checkpoint system not available[/red]")
                return

            parts = cmd.split()
            checkpoint_id = None

            if len(parts) > 1:
                if parts[1] == "last":
                    # Get last checkpoint
                    checkpoints = self.checkpoint_manager.list_checkpoints(limit=1)
                    if checkpoints:
                        checkpoint_id = checkpoints[0].checkpoint_id
                else:
                    checkpoint_id = parts[1]

            if not checkpoint_id:
                # Show list and prompt
                checkpoints = self.checkpoint_manager.list_checkpoints(limit=10)
                if not checkpoints:
                    self.console.print("[yellow]No checkpoints available[/yellow]")
                    return

                self.checkpoint_display.display_checkpoint_list(checkpoints)
                from rich.prompt import Prompt
                checkpoint_id = Prompt.ask("[bold]Enter checkpoint ID to restore[/bold]")

            # Get checkpoint
            checkpoint = self.checkpoint_manager.get_checkpoint(checkpoint_id)
            if not checkpoint:
                self.console.print(f"[red]Checkpoint not found: {checkpoint_id}[/red]")
                return

            # Confirm restore
            if not self.checkpoint_display.confirm_restore(checkpoint):
                self.console.print("[yellow]Restore cancelled[/yellow]")
                return

            # Restore checkpoint
            try:
                restored = self.checkpoint_manager.restore_checkpoint(checkpoint_id)
                self.checkpoint_display.display_restore_summary(checkpoint, restored)
            except Exception as e:
                self.console.print(f"[red]Failed to restore checkpoint: {e}[/red]")

        elif cmd.startswith("/diff"):
            # Compare files
            parts = cmd.split()
            if len(parts) < 3:
                self.console.print("[yellow]Usage: /diff <file1> <file2>[/yellow]")
                return

            file1 = parts[1]
            file2 = parts[2]

            try:
                self.diff_preview.compare_files(file1, file2, display=True)
            except Exception as e:
                self.console.print(f"[red]Error comparing files: {e}[/red]")

        else:
            self.console.print(f"[red]Unknown command: {command}[/red]")

    async def process_request(self, user_input: str):
        """Process user request with AI, streaming, and comprehensive error handling"""
        try:
            logger.info(f"Processing user request: {user_input[:100]}...")

            # Save user message to history
            if self.history_manager:
                self.history_manager.add_message("user", user_input)

            # Save to repo config history as well
            if self.repo_config:
                try:
                    self.repo_config.add_message("user", user_input)
                except Exception as e:
                    logger.error(f"Failed to log user message to repo config: {e}")

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
            has_function_calls = False

            # Stream the response
            async for chunk in self.provider.send_message_stream(user_input):
                try:
                    # Check for function calls
                    if chunk.function_calls:
                        has_function_calls = True
                        # Handle function calls (need to break streaming)
                        tool_result_content = await self.execute_function_calls_provider(chunk)

                        # Send tool results and get final response
                        response = await self.provider.send_message(tool_result_content)

                        # Display the final response
                        if response.content:
                            accumulated_text += response.content
                            self.display_response(response.content)

                        break  # Exit streaming loop

                    # Handle text streaming
                    elif chunk.content:
                        accumulated_text += chunk.content
                        self.console.print(chunk.content, end="")

                except Exception as e:
                    logger.error(f"Error processing chunk: {e}")
                    continue

            # Newline after streaming (only if not function call)
            if not has_function_calls:
                self.console.print()

            # Save assistant response to history
            if self.history_manager and accumulated_text:
                self.history_manager.add_message("model", accumulated_text)

            # Save to repo config history as well
            if self.repo_config and accumulated_text:
                try:
                    self.repo_config.add_message("assistant", accumulated_text)
                except Exception as e:
                    logger.error(f"Failed to log assistant message to repo config: {e}")

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
                response = await self.provider.send_message(user_input)

            # Handle function calls and responses
            try:
                while response.function_calls:
                    # Handle function calls
                    tool_result_content = await self.execute_function_calls_provider(response)

                    # Show loading indicator while processing tool results
                    with self.console.status(
                        "[cyan]Processing results...[/cyan]", spinner="dots"
                    ):
                        response = await self.provider.send_message(tool_result_content)

                # Display text response
                if response.content:
                    self.display_response(response.content)

                    # Save to history
                    if self.history_manager:
                        self.history_manager.add_message("model", response.content)

                    # Save to repo config history as well
                    if self.repo_config:
                        try:
                            self.repo_config.add_message("assistant", response.content)
                        except Exception as e:
                            logger.error(f"Failed to log assistant message to repo config: {e}")

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

    async def execute_function_calls_provider(self, response: ProviderResponse):
        """Execute function calls from any provider response"""
        if not response.function_calls:
            return None

        # Convert function calls to dict format for plan mode
        function_calls_list = [
            {
                "id": fc.id,
                "name": fc.name,
                "arguments": fc.arguments
            }
            for fc in response.function_calls
        ]

        # Check if we should use plan mode
        use_plan_mode = self.plan_executor.should_use_plan_mode(
            function_calls_list,
            self.config
        )

        # Execute with or without plan mode
        if use_plan_mode:
            # Use plan mode - creates plan and requests approval
            success, results = await self.plan_executor.execute_with_plan(
                user_request="[AI-generated operations]",
                function_calls=function_calls_list,
                tool_executor=self._execute_single_tool_with_permission,
                ai_summary=response.content or None
            )

            if not success:
                # Plan was rejected
                tool_results = [
                    {
                        "id": fc.id,
                        "name": fc.name,
                        "result": "Plan rejected by user"
                    }
                    for fc in response.function_calls
                ]
            else:
                # Create tool results from plan execution
                tool_results = []
                for i, fc in enumerate(response.function_calls):
                    result = results[i] if i < len(results) else "No result"
                    tool_results.append({
                        "id": fc.id,
                        "name": fc.name,
                        "result": result
                    })
        else:
            # Normal execution without plan mode
            tool_results = []

            for fc in response.function_calls:
                tool_name = fc.name
                tool_args = fc.arguments

                self.console.print(f"\n[dim]→ Calling tool: {tool_name}[/dim]")

                # Request permission for file operations
                if not await self.request_permission(tool_name, tool_args):
                    result = "Operation cancelled by user"
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

                tool_results.append({
                    "id": fc.id,
                    "name": tool_name,
                    "result": result
                })

        # Format results based on provider type
        return self._format_tool_results(tool_results)

    async def _execute_single_tool_with_permission(self, tool_name: str, tool_args: dict) -> str:
        """Execute a single tool with permission check (for plan executor)

        Args:
            tool_name: Name of the tool
            tool_args: Tool arguments

        Returns:
            Tool execution result
        """
        # Request permission for file operations
        if not await self.request_permission(tool_name, tool_args):
            return "Operation cancelled by user"

        # Execute the tool
        result = await self.tool_registry.execute_tool(tool_name, tool_args)
        return result

    def _format_tool_results(self, tool_results: List[Dict[str, Any]]):
        """Format tool results for provider consumption"""
        provider_name = self.config.model.provider.lower()

        if provider_name == "gemini":
            # Gemini format
            function_response_parts = []
            for tr in tool_results:
                function_response_parts.append(
                    protos.Part(
                        function_response=protos.FunctionResponse(
                            name=tr["name"],
                            response={"result": tr["result"]}
                        )
                    )
                )
            return protos.Content(role="user", parts=function_response_parts)

        elif provider_name == "openai":
            # OpenAI format
            return {
                "role": "tool",
                "tool_call_id": tool_results[0]["id"],  # OpenAI expects one at a time
                "content": tool_results[0]["result"]
            }

        elif provider_name in ["anthropic", "claude"]:
            # Anthropic format
            return {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tr["id"],
                        "content": tr["result"]
                    }
                    for tr in tool_results
                ]
            }

        elif provider_name == "ollama":
            # Ollama uses OpenAI-compatible format
            return {
                "role": "tool",
                "content": tool_results[0]["result"]
            }

        else:
            # Default: return as-is
            return tool_results

    async def execute_function_calls(self, response):
        """
        DEPRECATED: Execute function calls from Gemini response

        This method is kept for backward compatibility but should not be used.
        Use execute_function_calls_provider instead.
        """
        return await self.execute_function_calls_provider(response)

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
