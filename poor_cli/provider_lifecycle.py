"""
Provider lifecycle service for poor-cli clients.

This module encapsulates provider creation, interactive provider switching,
and provider listing, with typed interfaces for dependencies.
"""

import asyncio
import os
from typing import Any, Dict, Optional, Protocol, Type

from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from .config import Config, ProviderConfig
from .exceptions import ConfigurationError, setup_logger
from .providers.base import BaseProvider
from .providers.provider_factory import ProviderFactory

logger = setup_logger(__name__)


class ConsoleLike(Protocol):
    """Console interface used by provider lifecycle operations."""

    def print(self, *objects: Any, **kwargs: Any) -> None:
        """Print rich content to the user."""


class ConfigManagerLike(Protocol):
    """Config manager operations required by provider lifecycle."""

    def get_api_key(self, provider: str) -> Optional[str]:
        """Return provider API key if available."""

    def get_provider_config(self, provider: str) -> Optional[ProviderConfig]:
        """Return provider configuration block."""

    def save(self) -> None:
        """Persist updated configuration."""


class ProviderFactoryLike(Protocol):
    """Factory interface for provider creation/listing."""

    @classmethod
    def create(
        cls,
        provider_name: str,
        api_key: str,
        model_name: str,
        **kwargs: Any,
    ) -> BaseProvider:
        """Create a provider instance."""

    @classmethod
    def list_providers(cls) -> Dict[str, Type[BaseProvider]]:
        """List registered provider types."""


class ProviderLifecycleService:
    """Handles provider lifecycle concerns for interactive clients."""

    def __init__(
        self,
        *,
        console: ConsoleLike,
        config: Config,
        config_manager: ConfigManagerLike,
        provider_factory: ProviderFactoryLike = ProviderFactory,
    ) -> None:
        self.console = console
        self.config = config
        self.config_manager = config_manager
        self.provider_factory = provider_factory

    async def initialize_provider(self) -> BaseProvider:
        """Initialize provider based on current config and API keys."""
        try:
            api_key = self.config_manager.get_api_key(self.config.model.provider)

            if not api_key and self.config.model.provider != "ollama":
                available_providers = self._providers_with_keys()
                if not available_providers:
                    provider_name = self.config.model.provider
                    provider_config = self.config.model.providers.get(provider_name)
                    env_var = provider_config.api_key_env_var if provider_config else "<missing-config>"
                    self.console.print(
                        Panel(
                            f"[bold red]API Key Not Found:[/bold red]\n\n"
                            f"No API key found for provider: {provider_name}\n\n"
                            f"[yellow]Please set the environment variable:[/yellow]\n"
                            f"{env_var}\n\n"
                            "Or add it to your .env file.",
                            title="⚠️  Configuration Error",
                            border_style="red",
                        )
                    )
                    logger.error("No API key for provider: %s", provider_name)
                    raise SystemExit(1)

                self.console.print(
                    Panel(
                        f"[yellow]No API key found for provider: {self.config.model.provider}[/yellow]\n\n"
                        "[cyan]Available providers with API keys:[/cyan]\n"
                        + "\n".join([f"  • {p}" for p in available_providers])
                        + "\n\n[bold]Would you like to switch to an available provider?[/bold]",
                        title="⚠️  Provider Configuration",
                        border_style="yellow",
                    )
                )

                response = await asyncio.to_thread(
                    Prompt.ask,
                    "[bold]Switch provider?[/bold]",
                    choices=["y", "n", "yes", "no"],
                    default="y",
                )

                if response.lower() in {"y", "yes"}:
                    switched = await self.switch_provider()
                    if switched is None:
                        raise SystemExit(0)
                    return switched

                self.console.print("[yellow]Exiting. Please set an API key and try again.[/yellow]")
                raise SystemExit(0)

            return self._create_provider(api_key)

        except ConfigurationError as e:
            self._render_configuration_error(e)
            raise SystemExit(1)

    async def switch_provider(self) -> Optional[BaseProvider]:
        """Interactively switch provider and return a newly initialized provider."""
        available_providers = self.provider_factory.list_providers()
        if not available_providers:
            self.console.print("[red]No providers available[/red]")
            return None

        self.console.print("\n[bold]Available Providers:[/bold]")
        provider_list = list(available_providers.keys())

        for index, provider_name in enumerate(provider_list, 1):
            current = " [green](current)[/green]" if provider_name == self.config.model.provider else ""
            provider_config = self.config.model.providers.get(provider_name)
            default_model = provider_config.default_model if provider_config else "N/A"
            has_key = provider_name == "ollama" or self.config_manager.get_api_key(provider_name) is not None
            key_status = "[green]✓[/green]" if has_key else "[red]✗ (no key)[/red]"
            self.console.print(f"  {index}. {provider_name} - {default_model}{current} {key_status}")

        choice = await asyncio.to_thread(
            Prompt.ask,
            "\n[bold]Select provider[/bold]",
            choices=[str(i) for i in range(1, len(provider_list) + 1)] + ["c"],
            default="c",
        )

        if choice == "c":
            self.console.print("[yellow]Cancelled[/yellow]")
            return None

        selected_provider = provider_list[int(choice) - 1]
        selected_config = self.config.model.providers.get(selected_provider)
        default_model = selected_config.default_model if selected_config else ""

        model_name = await asyncio.to_thread(
            Prompt.ask,
            "\n[bold]Model name[/bold]",
            default=default_model,
        )

        self.config.model.provider = selected_provider
        self.config.model.model_name = model_name
        self.config_manager.save()

        self.console.print(f"\n[cyan]Switching to {selected_provider} ({model_name})...[/cyan]")
        return await self.initialize_provider()

    async def list_all_providers(self) -> None:
        """Display all configured providers and readiness status."""
        try:
            table = Table(title="Available AI Providers", show_header=True, header_style="bold cyan")
            table.add_column("Provider", style="cyan", width=12)
            table.add_column("Status", width=10)
            table.add_column("Default Model", style="green", width=30)
            table.add_column("API Key", width=15)
            table.add_column("Base URL", width=25)

            for provider_name, provider_config in self.config.model.providers.items():
                api_key_var = provider_config.api_key_env_var
                api_key_value = os.getenv(api_key_var, "")

                if provider_name == self.config.model.provider:
                    status = "[green]● Active[/green]"
                elif api_key_value or provider_name == "ollama":
                    status = "[yellow]○ Ready[/yellow]"
                else:
                    status = "[red]○ No Key[/red]"

                if provider_name == "ollama":
                    key_status = "[dim]Not needed[/dim]"
                elif api_key_value:
                    masked_key = f"{api_key_value[:8]}...{api_key_value[-4:]}" if len(api_key_value) > 12 else "***"
                    key_status = f"[green]{masked_key}[/green]"
                else:
                    key_status = f"[red]{api_key_var}[/red]"

                base_url = provider_config.base_url if provider_config.base_url else "[dim]Default[/dim]"

                table.add_row(
                    provider_name.capitalize(),
                    status,
                    provider_config.default_model,
                    key_status,
                    base_url,
                )

            self.console.print(table)

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
            logger.error("Error listing providers: %s", e, exc_info=True)

    def _providers_with_keys(self) -> list[str]:
        """Return provider names that can be initialized with current credentials."""
        providers: list[str] = []
        for provider_name in self.config.model.providers.keys():
            if provider_name == "ollama" or self.config_manager.get_api_key(provider_name):
                providers.append(provider_name)
        return providers

    def _create_provider(self, api_key: Optional[str]) -> BaseProvider:
        """Create a provider instance from the active provider configuration."""
        provider_name = self.config.model.provider
        logger.info("Creating %s provider...", provider_name)

        provider_config = self.config_manager.get_provider_config(provider_name)
        extra_kwargs: Dict[str, Any] = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url

        provider = self.provider_factory.create(
            provider_name=provider_name,
            api_key=api_key or "",
            model_name=self.config.model.model_name,
            **extra_kwargs,
        )

        logger.info("Provider %s initialized successfully", provider_name)
        return provider

    def _render_configuration_error(self, error: ConfigurationError) -> None:
        """Render configuration failure details and recovery hints."""
        error_msg = str(error)
        if "API key" in error_msg or "GEMINI_API_KEY" in error_msg:
            recovery_steps = [
                "1. Get a free API key from https://makersuite.google.com/app/apikey",
                "2. Add it to your .env file: GEMINI_API_KEY=your-key-here",
                "3. Or set environment variable: export GEMINI_API_KEY=your-key-here",
                "4. Restart poor-cli",
            ]
        elif "provider" in error_msg.lower():
            recovery_steps = [
                "1. Use /providers to see available providers",
                "2. Use /switch to change providers",
                "3. Check ~/.poor-cli/config.yaml for configuration",
                "4. Ensure API keys are set in .env file",
            ]
        else:
            recovery_steps = [
                "1. Check ~/.poor-cli/config.yaml for errors",
                "2. Verify all required environment variables are set",
                "3. Try: poor-cli --verbose for detailed logs",
                "4. Reset config: rm ~/.poor-cli/config.yaml",
            ]

        recovery_text = "\n\n[bold cyan]How to fix this:[/bold cyan]\n" + "\n".join(recovery_steps)
        self.console.print(
            Panel(
                f"[bold red]Configuration Error:[/bold red]\n{error}\n\n"
                f"[yellow]Provider:[/yellow] {self.config.model.provider}\n"
                f"[yellow]Model:[/yellow] {self.config.model.model_name}"
                f"{recovery_text}",
                title="⚠️  Configuration Error",
                border_style="red",
            )
        )
        logger.error("Configuration error: %s", error)
