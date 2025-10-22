"""
REPL interface for poor-cli
"""

import sys
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.syntax import Syntax
from rich import print as rprint
from google.generativeai import types

from .gemini_client import GeminiClient
from .tools import ToolRegistry


class PoorCLI:
    """Main REPL interface"""

    def __init__(self):
        self.console = Console()
        self.client = None
        self.tool_registry = ToolRegistry()
        self.running = False

    def initialize(self):
        """Initialize the Gemini client and tools"""
        try:
            self.client = GeminiClient()
            tool_declarations = self.tool_registry.get_tool_declarations()
            self.client.set_tools(tool_declarations)

            self.console.print(Panel.fit(
                "[bold cyan]poor-cli[/bold cyan] v0.1.0\n"
                "AI-powered CLI tool using Gemini\n\n"
                "Commands:\n"
                "  /help  - Show this help\n"
                "  /quit  - Exit the REPL\n"
                "  /clear - Clear conversation history",
                title="Welcome",
                border_style="cyan"
            ))

        except ValueError as e:
            self.console.print(f"[bold red]Error:[/bold red] {e}", style="red")
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
            self.console.print(Panel.fit(
                "[bold]Available Commands:[/bold]\n\n"
                "/help  - Show this help message\n"
                "/quit  - Exit the REPL\n"
                "/clear - Clear conversation history\n\n"
                "[bold]Available Tools:[/bold]\n"
                "- read_file: Read file contents\n"
                "- write_file: Write to files\n"
                "- edit_file: Edit files\n"
                "- glob_files: Find files by pattern\n"
                "- grep_files: Search in files\n"
                "- bash: Execute bash commands",
                title="Help",
                border_style="cyan"
            ))

        elif cmd == "/clear":
            # Reinitialize to clear history
            self.client.set_tools(self.tool_registry.get_tool_declarations())
            self.console.print("[green]Conversation history cleared[/green]")

        else:
            self.console.print(f"[red]Unknown command: {command}[/red]")

    def process_request(self, user_input: str):
        """Process user request with AI"""
        try:
            # Show loading indicator
            with self.console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
                # Send message to Gemini
                response = self.client.send_message(user_input)

            # Handle function calls
            while response.candidates[0].content.parts:
                part = response.candidates[0].content.parts[0]

                # Check if this is a function call
                if hasattr(part, 'function_call') and part.function_call:
                    tool_result_content = self.execute_function_calls(response)

                    # Show loading indicator while processing tool results
                    with self.console.status("[cyan]Processing results...[/cyan]", spinner="dots"):
                        response = self.client.send_message(tool_result_content)

                # Check if this is text response
                elif hasattr(part, 'text'):
                    self.display_response(part.text)
                    break
                else:
                    break

        except Exception as e:
            self.console.print(f"[bold red]Error:[/bold red] {str(e)}", style="red")

    def execute_function_calls(self, response):
        """Execute function calls from Gemini response"""
        function_response_parts = []

        for part in response.candidates[0].content.parts:
            if hasattr(part, 'function_call') and part.function_call:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args)

                self.console.print(f"\n[dim]→ Calling tool: {tool_name}[/dim]")

                # Execute the tool
                result = self.tool_registry.execute_tool(tool_name, tool_args)

                # Display tool output
                if result:
                    self.console.print(Panel(
                        result[:1000] + ("..." if len(result) > 1000 else ""),
                        title=f"Tool Output: {tool_name}",
                        border_style="dim",
                        expand=False
                    ))

                # Prepare result for Gemini using proper SDK types
                function_response_parts.append(
                    types.Part.from_function_response(
                        name=tool_name,
                        response={"result": result}
                    )
                )

        # Return as a Content object with role="user"
        return types.Content(
            role="user",
            parts=function_response_parts
        )

    def display_response(self, text: str):
        """Display AI response with markdown formatting"""
        self.console.print("\n[bold green]Assistant[/bold green]")

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
