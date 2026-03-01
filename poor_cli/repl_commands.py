"""
Slash command handlers for PoorCLIAsync.
"""

import asyncio

from rich.panel import Panel
from rich.prompt import Prompt

from .config import PermissionMode
from .exceptions import disable_verbose_logging, enable_verbose_logging, setup_logger

logger = setup_logger(__name__)

async def handle_slash_command(repl, command: str):
    """Handle slash commands"""
    cmd = command.lower().strip()

    if cmd == "/quit" or cmd == "/exit":
        repl.running = False

    elif cmd == "/help":
        repl.console.print(
            Panel.fit(
                "[bold]Available Commands:[/bold]\n\n"
                "[cyan]Session Management:[/cyan]\n"
                "/help          - Show this help message\n"
                "/quit          - Exit the REPL\n"
                "/clear         - Clear current conversation\n"
                "/clear-output  - Clear screen, keep history\n"
                "/history [N]   - Show recent messages (default: 10)\n"
                "/sessions      - List all previous sessions\n"
                "/new-session   - Start fresh (clear history)\n"
                "/retry         - Retry last request\n"
                "/search <term> - Search conversation history\n"
                "/edit-last     - Edit and resend last message\n"
                "/copy          - Copy last response to clipboard\n\n"
                "[cyan]Checkpoints & Undo:[/cyan]\n"
                "/checkpoints   - List all checkpoints\n"
                "/checkpoint    - Create manual checkpoint\n"
                "/save          - Quick checkpoint (alias)\n"
                "/rewind [ID]   - Restore checkpoint (ID or 'last')\n"
                "/undo          - Quick restore last checkpoint\n"
                "/restore       - Quick restore (alias for /undo)\n"
                "/diff <f1> <f2> - Compare two files\n\n"
                "[cyan]Provider Management:[/cyan]\n"
                "/provider      - Show current provider info\n"
                "/providers     - List all available providers and models\n"
                "/switch        - Switch AI provider\n\n"
                "[cyan]Export & Archive:[/cyan]\n"
                "/export [format] - Export conversation (json, md, txt)\n\n"
                "[cyan]Configuration:[/cyan]\n"
                "/config        - Show current configuration\n"
                "/permission-mode [mode] - Show or set permission mode\n"
                "/verbose       - Toggle verbose logging\n"
                "/plan-mode     - Toggle plan mode\n"
                "/cost          - Show API usage and cost estimates\n"
                "/model-info    - Show detailed model capabilities\n\n"
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
        await repl.provider.clear_history()
        if repl.history_manager:
            repl.history_manager.clear_current_session()
        repl.console.print("[green]Conversation history cleared[/green]")

    elif cmd == "/clear-output":
        # Clear screen but keep history
        import os
        os.system('clear' if os.name != 'nt' else 'cls')
        repl.console.print("[dim]Screen cleared (history preserved)[/dim]")

    elif cmd == "/provider":
        # Show current provider info
        caps = repl.provider.get_capabilities()
        provider_info = f"""[bold]Current Provider:[/bold] {repl.config.model.provider}
[bold]Model:[/bold] {repl.config.model.model_name}

[bold]Capabilities:[/bold]
  Streaming: {'✓' if caps.supports_streaming else '✗'}
  Function Calling: {'✓' if caps.supports_function_calling else '✗'}
  Vision: {'✓' if caps.supports_vision else '✗'}
  Max Context: {caps.max_context_tokens:,} tokens
"""
        repl.console.print(Panel(provider_info, title="Provider Info", border_style="cyan"))

    elif cmd == "/switch":
        # Switch provider
        await repl._switch_provider()

    elif cmd == "/providers":
        # List all available providers and their models
        await repl._list_all_providers()

    elif cmd == "/sessions":
        # List all previous sessions
        await repl._list_sessions()

    elif cmd == "/new-session":
        # Start a completely new session (clear history)
        await repl.provider.clear_history()
        if repl.history_manager:
            repl.history_manager.end_session()
            repl.history_manager.start_session(repl.config.model.model_name)
        if repl.repo_config:
            repl.repo_config.end_session()
            repl.repo_config.start_session(model=repl.config.model.model_name)
        repl.console.print("[green]✓ Started new session (previous history cleared)[/green]")

    elif cmd == "/config":
        config_display = repl.config_manager.display_config()
        repl.console.print(
            Panel(
                config_display,
                title="Current Configuration",
                border_style="cyan",
            )
        )

    elif cmd == "/permission-mode" or cmd.startswith("/permission-mode "):
        parts = cmd.split(maxsplit=1)
        if len(parts) == 1:
            current_mode = repl.config.security.permission_mode
            if isinstance(current_mode, PermissionMode):
                current_mode = current_mode.value
            repl.console.print(
                f"[cyan]Current permission mode:[/cyan] {current_mode}\n"
                "[dim]Available: prompt, auto-safe, danger-full-access[/dim]"
            )
            return

        requested_mode = parts[1].strip().lower()
        try:
            mode = PermissionMode(requested_mode)
        except ValueError:
            repl.console.print(
                "[red]Invalid permission mode.[/red] "
                "Use one of: prompt, auto-safe, danger-full-access."
            )
            return

        repl._set_permission_mode(mode)
        repl.console.print(f"[green]Permission mode set to {mode.value}[/green]")

    elif cmd == "/history" or cmd.startswith("/history "):
        # Show recent messages from chat history
        if not repl.repo_config:
            repl.console.print("[yellow]History tracking not available[/yellow]")
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
                    repl.console.print(f"[yellow]Invalid number: {parts[1]}. Using default (10)[/yellow]")

            # Get recent messages
            if not repl.repo_config.current_session:
                repl.console.print("[yellow]No active session[/yellow]")
                return

            recent_msgs = repl.repo_config.get_recent_messages(message_count)

            if not recent_msgs:
                repl.console.print("[yellow]No messages in current session[/yellow]")
                return

            # Display messages
            history_text = ""
            for msg in recent_msgs:
                role_color = "cyan" if msg.role == "user" else "green"
                role_name = "You" if msg.role == "user" else "AI"
                history_text += f"[{role_color}]{role_name}:[/{role_color}] {msg.content}\n\n"

            repl.console.print(
                Panel(
                    history_text.strip(),
                    title=f"Chat History (last {len(recent_msgs)} messages)",
                    border_style="cyan",
                )
            )

        except Exception as e:
            repl.console.print(f"[red]Error displaying history: {e}[/red]")
            logger.exception("Error in /history command")

    elif cmd == "/verbose":
        # Toggle verbose mode
        repl.verbose_mode = not repl.verbose_mode
        if repl.verbose_mode:
            enable_verbose_logging()
            repl.console.print("[green]Verbose logging enabled (INFO/DEBUG messages will be shown)[/green]")
        else:
            disable_verbose_logging()
            repl.console.print("[green]Verbose logging disabled (only WARNING/ERROR messages will be shown)[/green]")

        # Save to config
        repl.config.ui.verbose_logging = repl.verbose_mode
        repl.config_manager.save()

    elif cmd == "/plan-mode":
        # Toggle plan mode
        repl.config.plan_mode.enabled = not repl.config.plan_mode.enabled
        if repl.config.plan_mode.enabled:
            repl.console.print("[green]Plan mode enabled (preview before execution)[/green]")
        else:
            repl.console.print("[yellow]Plan mode disabled (direct execution)[/yellow]")
        repl.config_manager.save()

    elif cmd == "/checkpoints":
        # List all checkpoints
        if not repl.checkpoint_manager or not repl.checkpoint_display:
            repl.console.print("[red]Checkpoint system not available[/red]")
            return

        checkpoints = repl.checkpoint_manager.list_checkpoints(limit=20)
        repl.checkpoint_display.display_checkpoint_list(checkpoints, show_details=True)
        repl.checkpoint_display.display_storage_info(repl.checkpoint_manager)

    elif cmd == "/checkpoint" or cmd == "/save":
        # Create manual checkpoint (/save is alias for /checkpoint)
        if not repl.checkpoint_manager or not repl.checkpoint_display:
            repl.console.print("[red]Checkpoint system not available[/red]")
            return

        # Get files in current directory
        from pathlib import Path
        current_files = list(Path.cwd().rglob("*.py"))[:10]  # First 10 Python files
        file_paths = [str(f) for f in current_files if f.is_file()]

        if not file_paths:
            repl.console.print("[yellow]No files found to checkpoint[/yellow]")
            return

        # Create checkpoint
        try:
            checkpoint = repl.checkpoint_manager.create_checkpoint(
                file_paths=file_paths,
                description="Manual checkpoint" if cmd == "/checkpoint" else "Quick save",
                operation_type="manual"
            )
            repl.checkpoint_display.display_checkpoint_created(checkpoint)
        except Exception as e:
            repl.console.print(f"[red]Failed to create checkpoint: {e}[/red]")

    elif cmd.startswith("/rewind") or cmd == "/undo" or cmd == "/restore":
        # Restore checkpoint (/undo and /restore are aliases for /rewind last)
        if not repl.checkpoint_manager or not repl.checkpoint_display:
            repl.console.print("[red]Checkpoint system not available[/red]")
            return

        parts = cmd.split()
        checkpoint_id = None

        # Handle /undo and /restore commands (always use last checkpoint)
        if cmd == "/undo" or cmd == "/restore":
            checkpoints = repl.checkpoint_manager.list_checkpoints(limit=1)
            if checkpoints:
                checkpoint_id = checkpoints[0].checkpoint_id
            else:
                action = "undo" if cmd == "/undo" else "restore"
                repl.console.print(f"[yellow]No checkpoints available to {action}[/yellow]")
                return
        elif len(parts) > 1:
            if parts[1] == "last":
                # Get last checkpoint
                checkpoints = repl.checkpoint_manager.list_checkpoints(limit=1)
                if checkpoints:
                    checkpoint_id = checkpoints[0].checkpoint_id
            else:
                checkpoint_id = parts[1]

        if not checkpoint_id:
            # Show list and prompt
            checkpoints = repl.checkpoint_manager.list_checkpoints(limit=10)
            if not checkpoints:
                repl.console.print("[yellow]No checkpoints available[/yellow]")
                return

            repl.checkpoint_display.display_checkpoint_list(checkpoints)
            from rich.prompt import Prompt
            checkpoint_id = Prompt.ask("[bold]Enter checkpoint ID to restore[/bold]")

        # Get checkpoint
        checkpoint = repl.checkpoint_manager.get_checkpoint(checkpoint_id)
        if not checkpoint:
            repl.console.print(f"[red]Checkpoint not found: {checkpoint_id}[/red]")
            return

        # Confirm restore
        if not repl.checkpoint_display.confirm_restore(checkpoint):
            repl.console.print("[yellow]Restore cancelled[/yellow]")
            return

        # Restore checkpoint
        try:
            restored = repl.checkpoint_manager.restore_checkpoint(checkpoint_id)
            repl.checkpoint_display.display_restore_summary(checkpoint, restored)
        except Exception as e:
            repl.console.print(f"[red]Failed to restore checkpoint: {e}[/red]")

    elif cmd.startswith("/diff"):
        # Compare files
        parts = cmd.split()
        if len(parts) < 3:
            repl.console.print("[yellow]Usage: /diff <file1> <file2>[/yellow]")
            return

        file1 = parts[1]
        file2 = parts[2]

        try:
            repl.diff_preview.compare_files(file1, file2, display=True)
        except Exception as e:
            repl.console.print(f"[red]Error comparing files: {e}[/red]")

    elif cmd.startswith("/export"):
        # Export conversation history
        await repl._export_conversation(cmd)

    elif cmd == "/retry":
        # Retry last user request
        if not repl.last_user_input:
            repl.console.print("[yellow]No previous request to retry[/yellow]")
            return

        repl.console.print(f"[dim]Retrying: {repl.last_user_input[:50]}...[/dim]")
        await repl.process_request(repl.last_user_input)

    elif cmd.startswith("/search"):
        # Search conversation history
        if not repl.repo_config:
            repl.console.print("[yellow]History tracking not available[/yellow]")
            return

        parts = cmd.split(maxsplit=1)
        if len(parts) < 2:
            repl.console.print("[yellow]Usage: /search <search_term>[/yellow]")
            return

        search_term = parts[1].lower()
        messages = repl.repo_config.get_recent_messages(count=1000)  # Search last 1000 messages

        if not messages:
            repl.console.print("[yellow]No messages to search[/yellow]")
            return

        # Search for matches
        matches = []
        for msg in messages:
            if search_term in msg.content.lower():
                matches.append(msg)

        if not matches:
            repl.console.print(f"[yellow]No matches found for: {search_term}[/yellow]")
            return

        # Display matches
        from rich.table import Table
        table = Table(title=f"Search Results: '{search_term}' ({len(matches)} matches)", show_header=True, header_style="bold cyan")
        table.add_column("Role", style="cyan", width=10)
        table.add_column("Preview", style="white", width=60)
        table.add_column("Time", style="dim", width=20)

        for msg in matches[:20]:  # Show first 20 matches
            role_name = "User" if msg.role == "user" else "Assistant"
            # Get preview with search term highlighted
            preview = msg.content[:150]
            if len(msg.content) > 150:
                preview += "..."

            table.add_row(role_name, preview, msg.timestamp)

        repl.console.print(table)

        if len(matches) > 20:
            repl.console.print(f"[dim]Showing 20 of {len(matches)} matches[/dim]")

    elif cmd == "/edit-last":
        # Edit and resend last message
        if not repl.last_user_input:
            repl.console.print("[yellow]No previous request to edit[/yellow]")
            return

        repl.console.print(f"[dim]Last request: {repl.last_user_input}[/dim]\n")

        # Get edited input from user
        edited_input = await asyncio.to_thread(
            Prompt.ask,
            "[bold]Edit message[/bold]",
            default=repl.last_user_input
        )

        if not edited_input.strip():
            repl.console.print("[yellow]Edit cancelled[/yellow]")
            return

        # Update last_user_input and process
        repl.last_user_input = edited_input
        repl.console.print(f"[dim]Sending edited request...[/dim]")
        await repl.process_request(edited_input)

    elif cmd == "/cost":
        # Display usage stats and estimated costs
        stats = repl.session_stats

        # Cost estimates (approximate, as of 2024)
        costs_per_million = {
            "gemini": {"input": 0.00, "output": 0.00},  # Free tier
            "openai-gpt4": {"input": 30.00, "output": 60.00},
            "openai-gpt3.5": {"input": 0.50, "output": 1.50},
            "anthropic": {"input": 3.00, "output": 15.00},
            "ollama": {"input": 0.00, "output": 0.00},  # Local
        }

        provider = repl.config.model.provider.lower()
        model_name = repl.config.model.model_name.lower()

        # Determine cost tier
        if provider == "gemini" or provider == "ollama":
            cost_key = provider
        elif provider == "openai":
            cost_key = "openai-gpt4" if "gpt-4" in model_name else "openai-gpt3.5"
        elif provider == "anthropic":
            cost_key = "anthropic"
        else:
            cost_key = "openai-gpt4"  # Default estimate

        costs = costs_per_million.get(cost_key, {"input": 0, "output": 0})

        # Calculate estimated cost
        input_cost = (stats["input_tokens_estimate"] / 1_000_000) * costs["input"]
        output_cost = (stats["output_tokens_estimate"] / 1_000_000) * costs["output"]
        total_cost = input_cost + output_cost

        # Build cost display
        cost_info = f"""[bold]Session Usage Statistics:[/bold]

[cyan]Requests:[/cyan] {stats['requests']}
[cyan]Input:[/cyan] {stats['input_chars']:,} chars (~{stats['input_tokens_estimate']:,} tokens)
[cyan]Output:[/cyan] {stats['output_chars']:,} chars (~{stats['output_tokens_estimate']:,} tokens)

[bold]Estimated Cost:[/bold]
[cyan]Provider:[/cyan] {repl.config.model.provider} ({repl.config.model.model_name})
[cyan]Input Cost:[/cyan] ${input_cost:.4f}
[cyan]Output Cost:[/cyan] ${output_cost:.4f}
[cyan]Total:[/cyan] [bold yellow]${total_cost:.4f}[/bold yellow]

[dim]Note: Costs are estimates based on approximate pricing.
Token estimates use ~4 chars per token heuristic.
Free tiers (Gemini, Ollama) show $0.00.[/dim]"""

        repl.console.print(Panel(cost_info, title="Usage & Cost", border_style="yellow"))

    elif cmd == "/copy":
        # Copy last assistant response to clipboard
        if not repl.last_assistant_response:
            repl.console.print("[yellow]No response to copy[/yellow]")
            return

        try:
            # Try using pyperclip if available
            import pyperclip
            pyperclip.copy(repl.last_assistant_response)
            repl.console.print(f"[green]✓ Copied {len(repl.last_assistant_response)} characters to clipboard[/green]")
        except ImportError:
            # Fallback: try using pbcopy (macOS) or xclip (Linux)
            import subprocess
            import platform

            try:
                if platform.system() == "Darwin":  # macOS
                    process = subprocess.Popen(['pbcopy'], stdin=subprocess.PIPE)
                    process.communicate(repl.last_assistant_response.encode('utf-8'))
                    repl.console.print(f"[green]✓ Copied {len(repl.last_assistant_response)} characters to clipboard[/green]")
                elif platform.system() == "Linux":
                    process = subprocess.Popen(['xclip', '-selection', 'clipboard'], stdin=subprocess.PIPE)
                    process.communicate(repl.last_assistant_response.encode('utf-8'))
                    repl.console.print(f"[green]✓ Copied {len(repl.last_assistant_response)} characters to clipboard[/green]")
                else:
                    # Windows or unsupported platform
                    repl.console.print(
                        "[yellow]Clipboard copy not available. Install pyperclip:[/yellow]\n"
                        "[dim]pip install pyperclip[/dim]"
                    )
            except Exception as e:
                repl.console.print(f"[red]Failed to copy to clipboard: {e}[/red]")
        except Exception as e:
            repl.console.print(f"[red]Failed to copy to clipboard: {e}[/red]")

    elif cmd == "/model-info":
        # Display detailed model capabilities and information
        caps = repl.provider.get_capabilities()
        provider_info = repl.config.model.provider
        model_info = repl.config.model.model_name

        # Build detailed info panel
        info_text = f"""[bold cyan]Current Model Configuration[/bold cyan]

[bold]Provider:[/bold] {provider_info}
[bold]Model:[/bold] {model_info}

[bold cyan]Capabilities[/bold cyan]

[bold]Streaming:[/bold] {'✓ Enabled' if caps.supports_streaming else '✗ Not Available'}
  Real-time token-by-token response generation

[bold]Function Calling:[/bold] {'✓ Enabled' if caps.supports_function_calling else '✗ Not Available'}
  Can execute tools (read_file, write_file, bash, etc.)

[bold]Vision:[/bold] {'✓ Enabled' if caps.supports_vision else '✗ Not Available'}
  Can process and understand images

[bold]Context Window:[/bold] {caps.max_context_tokens:,} tokens
  Maximum conversation length before pruning

[bold cyan]Performance Characteristics[/bold cyan]

"""
        # Add provider-specific info
        if provider_info.lower() == "gemini":
            info_text += """[bold]Gemini Models:[/bold]
  • Free tier available
  • Fast inference
  • Good at code generation
  • Strong multilingual support
"""
        elif provider_info.lower() == "openai":
            info_text += """[bold]OpenAI Models:[/bold]
  • GPT-4: Most capable, slower, higher cost
  • GPT-3.5: Fast, cost-effective, good quality
  • Strong reasoning and instruction following
"""
        elif provider_info.lower() == "anthropic":
            info_text += """[bold]Anthropic Models:[/bold]
  • Claude 3.5 Sonnet: Balanced capability
  • Strong at analysis and code review
  • Large context windows (200k tokens)
"""
        elif provider_info.lower() == "ollama":
            info_text += """[bold]Ollama (Local):[/bold]
  • Runs entirely on your machine
  • No API costs
  • Privacy-focused (no data sent externally)
  • Speed depends on hardware
"""

        info_text += f"""\n[dim]Use /switch to change providers or models
Use /provider for a quick capability summary[/dim]"""

        repl.console.print(Panel(info_text, title="Model Information", border_style="cyan"))

    else:
        repl.console.print(f"[red]Unknown command: {command}[/red]\n"
                         "[dim]Type /help to see available commands[/dim]")

