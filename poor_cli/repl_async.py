"""
Async REPL interface for poor-cli with streaming support
"""

import argparse
import json
import os
import sys
import asyncio
import time
from typing import Optional, List, Dict, Any
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
from .config import get_config_manager, Config, PermissionMode
from .prompts import build_tool_calling_system_instruction
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
)
from .enhanced_input import EnhancedInputManager

# Setup logger
logger = setup_logger(__name__)


class PoorCLIAsync:
    """Async REPL interface with streaming support and multi-provider support"""

    def __init__(
        self,
        provider_override: Optional[str] = None,
        model_override: Optional[str] = None,
        cwd_override: Optional[str] = None,
        permission_mode_override: Optional[str] = None,
        dangerously_skip_permissions: bool = False,
    ):
        self.console = Console()
        self.provider: Optional[BaseProvider] = None

        if cwd_override:
            try:
                os.chdir(cwd_override)
                logger.info(f"Changed working directory to {os.getcwd()}")
            except OSError as e:
                raise ConfigurationError(f"Invalid --cwd path '{cwd_override}': {e}") from e

        self.config_manager = get_config_manager()
        self.config: Config = self.config_manager.config
        if provider_override:
            self.config.model.provider = provider_override
        if model_override:
            self.config.model.model_name = model_override
        self._apply_permission_mode_overrides(
            permission_mode_override=permission_mode_override,
            dangerously_skip_permissions=dangerously_skip_permissions,
        )
        self.history_manager: Optional[HistoryManager] = None
        self.repo_config: Optional[RepoConfig] = None  # For local JSON history
        self.error_recovery = ErrorRecoveryManager()
        self.running = False
        self.verbose_mode = self.config.ui.verbose_logging
        self.last_user_input: Optional[str] = None  # Track last user input for /retry
        self.last_assistant_response: Optional[str] = None  # Track last response for /copy

        # Usage tracking for /cost
        self.session_stats = {
            "requests": 0,
            "input_chars": 0,
            "output_chars": 0,
            "input_tokens_estimate": 0,
            "output_tokens_estimate": 0
        }

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

        # Initialize enhanced input manager for smart history
        self.input_manager = EnhancedInputManager()

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

    def _apply_permission_mode_overrides(
        self,
        permission_mode_override: Optional[str],
        dangerously_skip_permissions: bool,
    ) -> None:
        """Apply session-only permission mode overrides from CLI flags."""
        current_mode = self.config.security.permission_mode
        if isinstance(current_mode, str):
            try:
                current_mode = PermissionMode(current_mode)
            except ValueError as e:
                raise ConfigurationError(
                    f"Invalid configured permission mode: {current_mode}"
                ) from e

        selected_mode = current_mode
        if permission_mode_override:
            try:
                selected_mode = PermissionMode(permission_mode_override)
            except ValueError as e:
                raise ConfigurationError(
                    "Invalid --permission-mode value. "
                    "Expected: prompt, auto-safe, danger-full-access."
                ) from e

        if dangerously_skip_permissions:
            selected_mode = PermissionMode.DANGER_FULL_ACCESS

        self._set_permission_mode(selected_mode)

    def _set_permission_mode(self, mode: PermissionMode) -> None:
        """Set active permission mode and keep legacy permission booleans in sync."""
        self.config.security.permission_mode = mode
        if mode == PermissionMode.DANGER_FULL_ACCESS:
            self.config.security.require_permission_for_write = False
            self.config.security.require_permission_for_bash = False
        else:
            self.config.security.require_permission_for_write = True
            self.config.security.require_permission_for_bash = True

    async def initialize(self, show_welcome: bool = True):
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
                system_instruction = build_tool_calling_system_instruction(current_dir)

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
            if show_welcome:
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
                # Check which providers have API keys available
                available_providers = []
                for prov_name in self.config.model.providers.keys():
                    if prov_name == "ollama":
                        available_providers.append(prov_name)
                    elif self.config_manager.get_api_key(prov_name):
                        available_providers.append(prov_name)

                if not available_providers:
                    # No providers available at all
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

                # Providers are available, prompt user to switch
                self.console.print(
                    Panel(
                        f"[yellow]No API key found for provider: {self.config.model.provider}[/yellow]\n\n"
                        f"[cyan]Available providers with API keys:[/cyan]\n"
                        + "\n".join([f"  • {p}" for p in available_providers]) +
                        f"\n\n[bold]Would you like to switch to an available provider?[/bold]",
                        title="⚠️  Provider Configuration",
                        border_style="yellow",
                    )
                )

                # Prompt user to switch
                response = await asyncio.to_thread(
                    Prompt.ask,
                    "[bold]Switch provider?[/bold]",
                    choices=["y", "n", "yes", "no"],
                    default="y"
                )

                if response.lower() in ["y", "yes"]:
                    # Let user switch provider
                    await self._switch_provider()
                    # _switch_provider already reinitializes, so just return
                    return
                else:
                    self.console.print("[yellow]Exiting. Please set an API key and try again.[/yellow]")
                    sys.exit(0)

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
            error_msg = str(e)
            recovery_steps = []

            # Provide specific recovery suggestions based on error type
            if "API key" in error_msg or "GEMINI_API_KEY" in error_msg:
                recovery_steps = [
                    "1. Get a free API key from https://makersuite.google.com/app/apikey",
                    "2. Add it to your .env file: GEMINI_API_KEY=your-key-here",
                    "3. Or set environment variable: export GEMINI_API_KEY=your-key-here",
                    "4. Restart poor-cli"
                ]
            elif "provider" in error_msg.lower():
                recovery_steps = [
                    "1. Use /providers to see available providers",
                    "2. Use /switch to change providers",
                    "3. Check ~/.poor-cli/config.yaml for configuration",
                    "4. Ensure API keys are set in .env file"
                ]
            else:
                recovery_steps = [
                    "1. Check ~/.poor-cli/config.yaml for errors",
                    "2. Verify all required environment variables are set",
                    "3. Try: poor-cli --verbose for detailed logs",
                    "4. Reset config: rm ~/.poor-cli/config.yaml"
                ]

            recovery_text = "\n\n[bold cyan]How to fix this:[/bold cyan]\n" + "\n".join(recovery_steps)

            self.console.print(
                Panel(
                    f"[bold red]Configuration Error:[/bold red]\n{e}\n\n"
                    f"[yellow]Provider:[/yellow] {self.config.model.provider}\n"
                    f"[yellow]Model:[/yellow] {self.config.model.model_name}"
                    f"{recovery_text}",
                    title="⚠️  Configuration Error",
                    border_style="red",
                )
            )
            logger.error(f"Configuration error: {e}")
            sys.exit(1)

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

        from poor_cli import __version__

        welcome_text = f"""{mascot}
[bold cyan]poor-cli[/bold cyan] [dim]v{__version__}[/dim]
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

            # Check if API key is available
            has_key = provider_name == "ollama" or self.config_manager.get_api_key(provider_name) is not None
            key_status = "[green]✓[/green]" if has_key else "[red]✗ (no key)[/red]"

            self.console.print(f"  {i}. {provider_name} - {default_model}{current} {key_status}")

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
            system_instruction = build_tool_calling_system_instruction(current_dir)

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

    async def _list_all_providers(self):
        """List all available providers and their models"""
        try:
            from rich.table import Table

            table = Table(title="Available AI Providers", show_header=True, header_style="bold cyan")
            table.add_column("Provider", style="cyan", width=12)
            table.add_column("Status", width=10)
            table.add_column("Default Model", style="green", width=30)
            table.add_column("API Key", width=15)
            table.add_column("Base URL", width=25)

            # Get all configured providers
            for provider_name, provider_config in self.config.model.providers.items():
                # Check if API key is available
                api_key_var = provider_config.api_key_env_var
                api_key_value = os.getenv(api_key_var, "")

                # Determine status
                if provider_name == self.config.model.provider:
                    status = "[green]● Active[/green]"
                elif api_key_value or provider_name == "ollama":
                    status = "[yellow]○ Ready[/yellow]"
                else:
                    status = "[red]○ No Key[/red]"

                # API key status
                if provider_name == "ollama":
                    key_status = "[dim]Not needed[/dim]"
                elif api_key_value:
                    masked_key = f"{api_key_value[:8]}...{api_key_value[-4:]}" if len(api_key_value) > 12 else "***"
                    key_status = f"[green]{masked_key}[/green]"
                else:
                    key_status = f"[red]{api_key_var}[/red]"

                # Base URL (if applicable)
                base_url = provider_config.base_url if provider_config.base_url else "[dim]Default[/dim]"

                table.add_row(
                    provider_name.capitalize(),
                    status,
                    provider_config.default_model,
                    key_status,
                    base_url
                )

            self.console.print(table)

            # Show additional info
            info_text = (
                "\n[bold]Available Models by Provider:[/bold]\n\n"
                "[cyan]Gemini (Free):[/cyan] gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash\n"
                "[cyan]OpenAI (Paid):[/cyan] gpt-4-turbo, gpt-4, gpt-3.5-turbo\n"
                "[cyan]Anthropic (Paid):[/cyan] claude-3-5-sonnet-20241022, claude-3-opus, claude-3-sonnet\n"
                "[cyan]Ollama (Local):[/cyan] llama3, codellama, mistral, phi3\n\n"
                "[dim]Use /switch to change providers or set DEFAULT_PROVIDER in .env[/dim]"
            )

            self.console.print(Panel(info_text, title="Model Information", border_style="cyan"))

        except Exception as e:
            self.console.print(f"[red]Error listing providers: {e}[/red]")
            logger.error(f"Error listing providers: {e}", exc_info=True)

    async def _export_conversation(self, cmd: str):
        """Export conversation history to file"""
        try:
            # Parse format
            parts = cmd.split()
            export_format = parts[1].lower() if len(parts) > 1 else "json"

            if export_format not in ["json", "md", "txt", "markdown"]:
                self.console.print(
                    "[yellow]Invalid format. Supported formats: json, md, txt[/yellow]\n"
                    "[dim]Usage: /export [json|md|txt][/dim]"
                )
                return

            # Normalize markdown format
            if export_format == "markdown":
                export_format = "md"

            # Check if history exists
            if not self.repo_config:
                self.console.print("[yellow]No conversation history available to export[/yellow]")
                return

            if not self.repo_config.current_session:
                self.console.print("[yellow]No active session to export[/yellow]")
                return

            # Get all messages from current session
            messages = self.repo_config.get_recent_messages(count=10000)  # Get all messages

            if not messages:
                self.console.print("[yellow]No messages in current session[/yellow]")
                return

            # Generate filename
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            session_id = self.repo_config.current_session[:8]
            filename = f"conversation_{session_id}_{timestamp}.{export_format}"

            # Export based on format
            import json

            if export_format == "json":
                # JSON export
                export_data = {
                    "session_id": self.repo_config.current_session,
                    "exported_at": datetime.now().isoformat(),
                    "provider": self.config.model.provider,
                    "model": self.config.model.model_name,
                    "message_count": len(messages),
                    "messages": [
                        {
                            "role": msg.role,
                            "content": msg.content,
                            "timestamp": msg.timestamp
                        }
                        for msg in messages
                    ]
                }

                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(export_data, f, indent=2, ensure_ascii=False)

            elif export_format == "md":
                # Markdown export
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(f"# Conversation Export\n\n")
                    f.write(f"**Session ID:** {self.repo_config.current_session}\n")
                    f.write(f"**Provider:** {self.config.model.provider}\n")
                    f.write(f"**Model:** {self.config.model.model_name}\n")
                    f.write(f"**Exported:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"**Messages:** {len(messages)}\n\n")
                    f.write("---\n\n")

                    for i, msg in enumerate(messages, 1):
                        role_name = "User" if msg.role == "user" else "Assistant"
                        f.write(f"## Message {i}: {role_name}\n\n")
                        f.write(f"*{msg.timestamp}*\n\n")
                        f.write(f"{msg.content}\n\n")
                        f.write("---\n\n")

            elif export_format == "txt":
                # Plain text export
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write("=" * 60 + "\n")
                    f.write("CONVERSATION EXPORT\n")
                    f.write("=" * 60 + "\n\n")
                    f.write(f"Session ID: {self.repo_config.current_session}\n")
                    f.write(f"Provider: {self.config.model.provider}\n")
                    f.write(f"Model: {self.config.model.model_name}\n")
                    f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Messages: {len(messages)}\n\n")
                    f.write("=" * 60 + "\n\n")

                    for i, msg in enumerate(messages, 1):
                        role_name = "USER" if msg.role == "user" else "ASSISTANT"
                        f.write(f"[{role_name}] {msg.timestamp}\n")
                        f.write("-" * 60 + "\n")
                        f.write(f"{msg.content}\n\n")

            # Success message
            file_size = os.path.getsize(filename)
            self.console.print(
                Panel(
                    f"[green]✓ Conversation exported successfully[/green]\n\n"
                    f"[bold]File:[/bold] {filename}\n"
                    f"[bold]Format:[/bold] {export_format.upper()}\n"
                    f"[bold]Messages:[/bold] {len(messages)}\n"
                    f"[bold]Size:[/bold] {file_size:,} bytes",
                    title="Export Complete",
                    border_style="green"
                )
            )

            logger.info(f"Exported conversation to {filename} ({len(messages)} messages)")

        except Exception as e:
            self.console.print(
                f"[red]Failed to export conversation:[/red] {e}\n"
                f"[dim]Please check file permissions and try again[/dim]"
            )
            logger.error(f"Error exporting conversation: {e}", exc_info=True)

    async def _shutdown_sessions(self):
        """End history sessions and persist repository-scoped history."""
        if self.history_manager:
            self.history_manager.end_session()

        if self.repo_config:
            try:
                self.repo_config.end_session()
                logger.info("Repo config session ended and history saved")
            except Exception as e:
                logger.error(f"Failed to end repo config session: {e}")

    async def run(self):
        """Main async REPL loop"""
        await self.initialize(show_welcome=True)
        self.running = True

        while self.running:
            try:
                # Build prompt with provider and model info (PS1-style)
                provider_short = self.config.model.provider[:4].upper()  # e.g., "GEMI", "OPEN", "ANTH"
                model_short = self.config.model.model_name.split('-')[-1][:8]  # Last part of model name
                prompt_text = f"\nYou ({provider_short}/{model_short}): "

                # Use enhanced input manager with smart history (arrow keys) and file path autocomplete
                user_input = await self.input_manager.get_input(
                    prompt_text=prompt_text,
                    enable_completer=True  # Enable file path autocomplete with Tab key
                )

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    await self.handle_command(user_input)
                    continue

                # Save user input for potential /retry
                self.last_user_input = user_input

                # Process AI request
                await self.process_request(user_input)

            except KeyboardInterrupt:
                self.console.print("\n[yellow]Use /quit to exit[/yellow]")
                continue
            except EOFError:
                break

        # Cleanup
        await self._shutdown_sessions()

        self.console.print("\n[cyan]Goodbye![/cyan]")

    async def run_non_interactive(self, prompt: str, output_format: str = "text") -> int:
        """Execute one request and return process exit code."""
        await self.initialize(show_welcome=False)

        try:
            payload = await self._process_request_non_interactive(prompt)

            if output_format == "json":
                print(json.dumps(payload, ensure_ascii=False))
            elif payload["ok"]:
                if payload["response"]:
                    print(payload["response"])
            else:
                error = payload.get("error") or {}
                print(f"Error: {error.get('message', 'Unknown error')}", file=sys.stderr)

            return 0 if payload["ok"] else 1
        finally:
            await self._shutdown_sessions()

    async def _process_request_non_interactive(self, user_input: str) -> Dict[str, Any]:
        """Process one request and return machine-readable payload."""
        start_time = time.time()
        self._capture_tool_results = True
        self._captured_tool_results: List[Dict[str, Any]] = []
        self._non_interactive_mode = True

        payload: Dict[str, Any] = {
            "ok": False,
            "response": "",
            "tool_calls": [],
            "error": None,
        }

        try:
            logger.info(f"Processing non-interactive request: {user_input[:100]}...")

            self.session_stats["requests"] += 1
            self.session_stats["input_chars"] += len(user_input)
            self.session_stats["input_tokens_estimate"] += len(user_input) // 4

            if self.history_manager:
                self.history_manager.add_message("user", user_input)

            if self.repo_config:
                try:
                    self.repo_config.add_message("user", user_input)
                except Exception as e:
                    logger.error(f"Failed to log user message to repo config: {e}")

            if self.config.ui.enable_streaming:
                response_text = await self._collect_response_streaming(user_input)
            else:
                response_text = await self._collect_response_non_streaming(user_input)

            payload["ok"] = True
            payload["response"] = response_text
            payload["tool_calls"] = list(self._captured_tool_results)
            payload["elapsed_seconds"] = round(time.time() - start_time, 3)

            if response_text:
                self.session_stats["output_chars"] += len(response_text)
                self.session_stats["output_tokens_estimate"] += len(response_text) // 4
                self.last_assistant_response = response_text

                if self.history_manager:
                    self.history_manager.add_message("model", response_text)

                if self.repo_config:
                    try:
                        self.repo_config.add_message("assistant", response_text)
                    except Exception as e:
                        logger.error(f"Failed to log assistant message to repo config: {e}")

            return payload

        except Exception as e:
            logger.exception("Non-interactive request failed")
            payload["ok"] = False
            payload["tool_calls"] = list(self._captured_tool_results)
            payload["error"] = {
                "type": type(e).__name__,
                "message": str(e),
            }
            payload["elapsed_seconds"] = round(time.time() - start_time, 3)
            return payload

        finally:
            self._capture_tool_results = False
            self._non_interactive_mode = False

    async def _collect_response_streaming(self, user_input: str) -> str:
        """Collect complete response text from streaming provider calls."""
        accumulated_text = ""

        async for chunk in self.provider.send_message_stream(user_input):
            if chunk.function_calls:
                tool_result_content = await self.execute_function_calls_provider(chunk)
                response = await self.provider.send_message(tool_result_content)

                if response.content:
                    accumulated_text += response.content

                while response.function_calls:
                    tool_result_content = await self.execute_function_calls_provider(response)
                    response = await self.provider.send_message(tool_result_content)
                    if response.content:
                        accumulated_text += response.content
                break

            if chunk.content:
                accumulated_text += chunk.content

        return accumulated_text

    async def _collect_response_non_streaming(self, user_input: str) -> str:
        """Collect complete response text from non-streaming provider calls."""
        response = await self.provider.send_message(user_input)
        accumulated_text = response.content or ""

        while response.function_calls:
            tool_result_content = await self.execute_function_calls_provider(response)
            response = await self.provider.send_message(tool_result_content)
            if response.content:
                accumulated_text += response.content

        return accumulated_text

    async def handle_command(self, command: str):
        """Handle slash commands."""
        from .repl_commands import handle_slash_command

        await handle_slash_command(self, command)

    async def process_request(self, user_input: str) -> bool:
        """Process one user request and return whether it succeeded."""
        # Track execution time
        start_time = time.time()

        try:
            logger.info(f"Processing user request: {user_input[:100]}...")

            # Track usage stats
            self.session_stats["requests"] += 1
            self.session_stats["input_chars"] += len(user_input)
            self.session_stats["input_tokens_estimate"] += len(user_input) // 4

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

            # Display execution time
            elapsed_time = time.time() - start_time
            if elapsed_time > 0.5:  # Only show if > 0.5 seconds
                self.console.print(f"[dim]⏱ {elapsed_time:.2f}s[/dim]")
            return True

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
            return False

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
            return False

    async def _process_request_streaming(self, user_input: str):
        """Process request with streaming responses"""
        try:
            self.console.print("\n[bold green]Poor AI[/bold green]")

            accumulated_text = ""
            has_function_calls = False

            # Stream the response
            try:
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

            except KeyboardInterrupt:
                # Handle Ctrl+C during streaming
                self.console.print("\n\n[yellow]⚠ Streaming interrupted by user[/yellow]")
                logger.info("Streaming interrupted by Ctrl+C")
                # Still save whatever was accumulated
                if accumulated_text:
                    self.console.print(f"[dim]Partial response received ({len(accumulated_text)} chars)[/dim]")

            # Newline after streaming (only if not function call)
            if not has_function_calls and accumulated_text:
                self.console.print()

            # Show token/character count if enabled
            if self.config.ui.show_token_count and accumulated_text:
                char_count = len(accumulated_text)
                # Rough token estimate: ~4 chars per token
                token_estimate = char_count // 4
                self.console.print(f"[dim]({char_count} chars, ~{token_estimate} tokens)[/dim]")

            # Track output stats
            if accumulated_text:
                self.session_stats["output_chars"] += len(accumulated_text)
                self.session_stats["output_tokens_estimate"] += len(accumulated_text) // 4
                self.last_assistant_response = accumulated_text

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
            # Suggest provider failover
            self.console.print("\n[dim]Hint: Use /switch to try a different provider[/dim]")
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
            # Suggest provider failover
            self.console.print("\n[dim]Hint: Use /switch to try a different provider[/dim]")
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
        permission_mode = self.config.security.permission_mode
        if isinstance(permission_mode, str):
            permission_mode = PermissionMode(permission_mode)
            self.config.security.permission_mode = permission_mode

        if permission_mode == PermissionMode.DANGER_FULL_ACCESS:
            return True

        if permission_mode == PermissionMode.AUTO_SAFE:
            if tool_name == "bash":
                command = tool_args.get("command", "").strip().lower()
                safe_commands = self.config.security.safe_commands
                destructive_commands = ["rm", "del", "format", "dd", "mkfs", "fdisk", ">", "sudo rm"]
                is_destructive = any(cmd in command for cmd in destructive_commands)
                return any(command.startswith(cmd) for cmd in safe_commands) and not is_destructive

            if tool_name in {"write_file", "edit_file", "delete_file"}:
                return False

            return True

        # Check config for permission requirements
        if tool_name == "bash" and not self.config.security.require_permission_for_bash:
            return True

        if tool_name in ["write_file", "edit_file"] and not self.config.security.require_permission_for_write:
            return True

        # Define which tools require permission
        file_operation_tools = {"write_file", "edit_file", "bash"}

        if tool_name not in file_operation_tools:
            return True

        # For bash commands, check if it's a safe read-only command or destructive
        if tool_name == "bash":
            command = tool_args.get("command", "").strip().lower()
            safe_commands = self.config.security.safe_commands

            # Check for destructive commands
            destructive_commands = ["rm", "del", "format", "dd", "mkfs", "fdisk", ">", "sudo rm"]
            is_destructive = any(cmd in command for cmd in destructive_commands)

            if any(command.startswith(cmd) for cmd in safe_commands) and not is_destructive:
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

            # Check if destructive
            destructive_commands = ["rm", "del", "format", "dd", "mkfs", "fdisk", ">", "sudo rm"]
            is_destructive = any(cmd in command.lower() for cmd in destructive_commands)

            if is_destructive:
                action_desc = f"[red bold]⚠️  DESTRUCTIVE COMMAND:[/red bold] {command}"
                details = f"[red]This command may delete or modify files/data![/red]\n[dim]Proceed with caution.[/dim]"
                border_color = "red"
            else:
                action_desc = f"[yellow]Execute bash command:[/yellow] {command}"
                details = f"[dim]This will run a shell command.[/dim]"
                border_color = "yellow"
        else:
            return True

        # Display permission request
        self.console.print(
            Panel(
                f"{action_desc}\n{details}\n\n[bold]Allow this operation?[/bold]",
                title="⚠️  Permission Required",
                border_style=border_color if tool_name == "bash" else "yellow",
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
                        "arguments": fc.arguments,
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
                        "arguments": fc.arguments,
                        "result": result
                    })
        else:
            # Normal execution without plan mode
            tool_results = []

            for fc in response.function_calls:
                tool_name = fc.name
                tool_args = fc.arguments

                if not getattr(self, "_non_interactive_mode", False):
                    self.console.print(f"\n[dim]→ Calling tool: {tool_name}[/dim]")

                # Request permission for file operations
                if not await self.request_permission(tool_name, tool_args):
                    result = "Operation cancelled by user"
                    self.console.print("[yellow]Operation cancelled[/yellow]")
                else:
                    # Execute the tool asynchronously
                    result = await self.tool_registry.execute_tool(tool_name, tool_args)

                # Display tool output
                if result and not getattr(self, "_non_interactive_mode", False):
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
                    "arguments": tool_args,
                    "result": result
                })

        if getattr(self, "_capture_tool_results", False):
            self._captured_tool_results.extend(
                {
                    "id": tr.get("id"),
                    "name": tr.get("name"),
                    "arguments": tr.get("arguments", {}),
                    "result": tr.get("result"),
                }
                for tr in tool_results
            )

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
        """Display AI response with markdown formatting and syntax highlighting"""
        self.console.print("\n[bold green]Poor AI[/bold green]")

        # Try to render as markdown if enabled (includes syntax highlighting for code blocks)
        if self.config.ui.markdown_rendering:
            try:
                # Rich's Markdown automatically applies syntax highlighting to code blocks
                # using the Pygments library with the default theme
                md = Markdown(text, code_theme="monokai", inline_code_theme="monokai")
                self.console.print(md)
            except Exception as e:
                # Fallback to plain text if markdown rendering fails
                logger.debug(f"Markdown rendering failed: {e}")
                self.console.print(text)
        else:
            self.console.print(text)


def main():
    """Entry point for async poor-cli"""
    try:
        common_parser = argparse.ArgumentParser(add_help=False)
        common_parser.add_argument(
            "--provider",
            help="Override provider for this session",
        )
        common_parser.add_argument(
            "--model",
            help="Override model for this session",
        )
        common_parser.add_argument(
            "--cwd",
            help="Run poor-cli in a specific working directory",
        )
        common_parser.add_argument(
            "--permission-mode",
            choices=[mode.value for mode in PermissionMode],
            help="Permission behavior for tool execution",
        )
        common_parser.add_argument(
            "--dangerously-skip-permissions",
            action="store_true",
            help="Disable permission prompts and allow all operations",
        )

        parser = argparse.ArgumentParser(
            prog="poor-cli",
            description="poor-cli interactive assistant",
            parents=[common_parser],
        )
        subparsers = parser.add_subparsers(dest="command")
        run_parser = subparsers.add_parser(
            "run",
            help='Run one non-interactive prompt and exit',
        )
        run_parser.add_argument("prompt", help="Prompt text to send")
        run_parser.add_argument(
            "--output",
            choices=["text", "json"],
            default="text",
            help="Output format for non-interactive mode",
        )
        args = parser.parse_args()

        repl = PoorCLIAsync(
            provider_override=args.provider,
            model_override=args.model,
            cwd_override=args.cwd,
            permission_mode_override=args.permission_mode,
            dangerously_skip_permissions=args.dangerously_skip_permissions,
        )
        if args.command == "run":
            exit_code = asyncio.run(
                repl.run_non_interactive(args.prompt, output_format=args.output)
            )
            sys.exit(exit_code)

        asyncio.run(repl.run())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
