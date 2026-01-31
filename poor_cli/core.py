"""
PoorCLI Core Engine - Headless AI coding assistant

This module provides a headless engine that can be used by CLI, Neovim, VSCode, etc.
It separates the core AI functionality from any specific UI implementation.
"""

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Tuple

from .config import ConfigManager, Config
from .providers.base import BaseProvider, ProviderResponse, FunctionCall
from .providers.provider_factory import ProviderFactory
from .tools_async import ToolRegistryAsync
from .checkpoint import CheckpointManager
from .history import HistoryManager
from .context import ContextManager, get_context_manager
from .prompts import build_fim_prompt as _build_fim_prompt, get_system_instruction
from .exceptions import (
    PoorCLIError,
    ConfigurationError,
    setup_logger,
)

logger = setup_logger(__name__)


class PoorCLICore:
    """
    Headless AI coding assistant engine.
    
    This is the core wrapper layer that can be used by any UI:
    - CLI (repl_async.py)
    - Neovim plugin (via JSON-RPC server)
    - VSCode extension (via HTTP server)
    - Any other integration
    
    Attributes:
        provider: The AI provider (Gemini, OpenAI, Claude, Ollama)
        tool_registry: Registry of available tools
        history_manager: Conversation history manager
        checkpoint_manager: File checkpoint/undo system
        config: Configuration object
    """
    
    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize PoorCLICore with optional config path.
        
        Args:
            config_path: Optional path to config file. If None, uses default.
        """
        self.provider: Optional[BaseProvider] = None
        self.tool_registry: Optional[ToolRegistryAsync] = None
        self.history_manager: Optional[HistoryManager] = None
        self.checkpoint_manager: Optional[CheckpointManager] = None
        self.config: Optional[Config] = None
        self._config_manager: Optional[ConfigManager] = None
        self._config_path = config_path
        self._initialized = False
        self._system_instruction: Optional[str] = None
        
        # Permission callback for file operations
        # Set this to a callable(tool_name: str, tool_args: dict) -> Awaitable[bool]
        self._permission_callback: Optional[Callable[[str, Dict], Any]] = None
        
        # Context manager for intelligent context gathering
        self._context_manager: Optional[ContextManager] = None
        
        logger.info("PoorCLICore instance created")
    
    async def initialize(
        self,
        provider_name: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None
    ) -> None:
        """
        Initialize the core engine with provider and tools.
        
        Args:
            provider_name: Provider to use (gemini, openai, anthropic, ollama).
                          If None, uses config default.
            model_name: Model to use. If None, uses config default.
            api_key: API key. If None, uses environment variable.
        
        Raises:
            ConfigurationError: If initialization fails.
        """
        try:
            logger.info("Initializing PoorCLICore...")
            
            # Load configuration
            self._config_manager = ConfigManager(self._config_path)
            self.config = self._config_manager.load()
            
            # Override config with provided values
            if provider_name:
                self.config.model.provider = provider_name
            if model_name:
                self.config.model.model_name = model_name
            
            # Get API key
            resolved_api_key = api_key
            if not resolved_api_key:
                resolved_api_key = self._config_manager.get_api_key(
                    self.config.model.provider
                )
            
            # Ollama doesn't require API key
            if not resolved_api_key and self.config.model.provider != "ollama":
                raise ConfigurationError(
                    f"No API key found for provider: {self.config.model.provider}. "
                    f"Set environment variable: "
                    f"{self.config.model.providers[self.config.model.provider].api_key_env_var}"
                )
            
            # Get provider config for additional settings
            provider_config = self._config_manager.get_provider_config(
                self.config.model.provider
            )
            extra_kwargs = {}
            if provider_config and provider_config.base_url:
                extra_kwargs["base_url"] = provider_config.base_url
            
            # Create provider via factory
            self.provider = ProviderFactory.create(
                provider_name=self.config.model.provider,
                api_key=resolved_api_key or "",
                model_name=self.config.model.model_name,
                **extra_kwargs
            )
            logger.info(f"Created {self.config.model.provider} provider")
            
            # Initialize tool registry
            self.tool_registry = ToolRegistryAsync()
            tool_declarations = self.tool_registry.get_tool_declarations()
            logger.info(f"Registered {len(tool_declarations)} tools")
            
            # Build system instruction
            import os
            current_dir = os.getcwd()
            self._system_instruction = self._build_system_instruction(current_dir)
            
            # Initialize provider with tools and system instruction
            await self.provider.initialize(
                tools=tool_declarations,
                system_instruction=self._system_instruction
            )
            
            # Initialize history manager if enabled
            if self.config.history.auto_save:
                self.history_manager = HistoryManager()
                self.history_manager.start_session(self.config.model.model_name)
                logger.info("History manager initialized")
            
            # Initialize checkpoint manager if enabled
            if self.config.checkpoint.enabled:
                self.checkpoint_manager = CheckpointManager()
                logger.info("Checkpoint manager initialized")
            
            # Initialize context manager
            self._context_manager = get_context_manager()
            logger.info("Context manager initialized")
            
            self._initialized = True
            logger.info("PoorCLICore initialization complete")
            
        except ConfigurationError:
            raise
        except Exception as e:
            logger.exception("Failed to initialize PoorCLICore")
            raise ConfigurationError(f"Initialization failed: {e}")
    
    def _build_system_instruction(self, current_dir: str) -> str:
        """
        Build system instruction for the AI.
        
        Args:
            current_dir: Current working directory.
        
        Returns:
            System instruction string.
        """
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

    async def send_message(
        self,
        message: str,
        context_files: Optional[List[str]] = None
    ) -> AsyncIterator[str]:
        """
        Send a message and yield streaming text chunks.
        
        This method handles function calls internally and yields only text content.
        
        Args:
            message: The message to send to the AI.
            context_files: Optional list of file paths to include as context.
        
        Yields:
            Text chunks as they arrive from the AI.
        
        Raises:
            PoorCLIError: If not initialized or message sending fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Sending message: {message[:100]}...")
        
        # Build context from files if provided
        full_message = message
        if context_files:
            # Use context manager for intelligent context gathering
            if self._context_manager:
                primary_file = context_files[0] if context_files else None
                additional_files = context_files[1:] if len(context_files) > 1 else None
                
                context_result = await self._context_manager.gather_context(
                    primary_file=primary_file,
                    additional_files=additional_files,
                    include_imports=True
                )
                
                if context_result.files:
                    context_str = self._context_manager.format_context_for_prompt(
                        context_result,
                        include_paths=True
                    )
                    full_message = f"{context_str}\n\nUser request: {message}"
                    logger.info(context_result.message)
            else:
                # Fallback to simple file reading
                context_parts = []
                for file_path in context_files:
                    try:
                        content = await self.tool_registry.read_file(file_path)
                        context_parts.append(f"=== {file_path} ===\n{content}")
                    except Exception as e:
                        logger.warning(f"Failed to read context file {file_path}: {e}")
                if context_parts:
                    full_message = "Context files:\n" + "\n\n".join(context_parts) + f"\n\nUser request: {message}"

        
        # Save to history
        if self.history_manager:
            self.history_manager.add_message("user", message)
        
        try:
            accumulated_text = ""
            
            async for chunk in self.provider.send_message_stream(full_message):
                # Check for function calls
                if chunk.function_calls:
                    # Handle function calls
                    tool_results = await self._handle_function_calls(chunk)
                    
                    # Send tool results and get final response
                    response = await self.provider.send_message(tool_results)
                    
                    if response.content:
                        accumulated_text += response.content
                        yield response.content
                    
                    # Check for more function calls in the response
                    while response.function_calls:
                        tool_results = await self._handle_function_calls(response)
                        response = await self.provider.send_message(tool_results)
                        if response.content:
                            accumulated_text += response.content
                            yield response.content
                    
                    break  # Exit streaming after handling function calls
                
                # Yield text content
                elif chunk.content:
                    accumulated_text += chunk.content
                    yield chunk.content
            
            # Save assistant response to history
            if self.history_manager and accumulated_text:
                self.history_manager.add_message("model", accumulated_text)
            
            logger.info(f"Message complete, {len(accumulated_text)} chars")
            
        except Exception as e:
            logger.exception("Error sending message")
            raise PoorCLIError(f"Failed to send message: {e}")

    async def _handle_function_calls(
        self,
        response: ProviderResponse
    ) -> Any:
        """
        Handle function calls from a provider response.
        
        Args:
            response: The provider response containing function calls.
        
        Returns:
            Formatted tool results for the provider.
        """
        if not response.function_calls:
            return None
        
        tool_results = []
        
        for fc in response.function_calls:
            tool_name = fc.name
            tool_args = fc.arguments
            
            logger.info(f"Executing tool: {tool_name}")
            
            # Check permission if callback is set
            if self._permission_callback:
                try:
                    permitted = await self._permission_callback(tool_name, tool_args)
                    if not permitted:
                        result = "Operation cancelled by user"
                        tool_results.append({
                            "id": fc.id,
                            "name": tool_name,
                            "result": result
                        })
                        continue
                except Exception as e:
                    logger.error(f"Permission callback error: {e}")
            
            # Execute the tool
            try:
                result = await self.tool_registry.execute_tool(tool_name, tool_args)
            except Exception as e:
                result = f"Error: {e}"
                logger.error(f"Tool execution failed: {e}")
            
            tool_results.append({
                "id": fc.id,
                "name": tool_name,
                "result": result
            })
        
        # Format results based on provider
        return self._format_tool_results(tool_results)

    def _format_tool_results(self, tool_results: List[Dict[str, Any]]) -> Any:
        """
        Format tool results for provider consumption.
        
        Args:
            tool_results: List of tool result dicts with id, name, result.
        
        Returns:
            Provider-specific formatted tool results.
        """
        provider_name = self.config.model.provider.lower()
        
        if provider_name == "gemini":
            # Gemini format using protos
            import google.generativeai as genai
            from google.generativeai import protos
            
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
            # OpenAI expects tool results one at a time in conversation
            return [
                {
                    "role": "tool",
                    "tool_call_id": tr["id"],
                    "content": tr["result"]
                }
                for tr in tool_results
            ]
        
        elif provider_name in ["anthropic", "claude"]:
            # Anthropic format
            return [
                {
                    "type": "tool_result",
                    "tool_use_id": tr["id"],
                    "content": tr["result"]
                }
                for tr in tool_results
            ]
        
        elif provider_name == "ollama":
            # Ollama uses OpenAI-compatible format
            return [
                {
                    "role": "tool",
                    "tool_call_id": tr["id"],
                    "content": tr["result"]
                }
                for tr in tool_results
            ]
        
        else:
            # Default: return as string
            return "\n".join([f"{tr['name']}: {tr['result']}" for tr in tool_results])

    async def send_message_sync(
        self,
        message: str,
        context_files: Optional[List[str]] = None
    ) -> str:
        """
        Send a message and return complete response text.
        
        This is a non-streaming version that waits for the complete response.
        Handles function calls internally.
        
        Args:
            message: The message to send to the AI.
            context_files: Optional list of file paths to include as context.
        
        Returns:
            Complete response text from the AI.
        
        Raises:
            PoorCLIError: If not initialized or message sending fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Sending message (sync): {message[:100]}...")
        
        # Build context from files if provided
        full_message = message
        if context_files:
            context_parts = []
            for file_path in context_files:
                try:
                    content = await self.tool_registry.read_file(file_path)
                    context_parts.append(f"=== {file_path} ===\n{content}")
                except Exception as e:
                    logger.warning(f"Failed to read context file {file_path}: {e}")
            if context_parts:
                full_message = "Context files:\n" + "\n\n".join(context_parts) + f"\n\nUser request: {message}"
        
        # Save to history
        if self.history_manager:
            self.history_manager.add_message("user", message)
        
        try:
            response = await self.provider.send_message(full_message)
            accumulated_text = response.content or ""
            
            # Handle function calls
            while response.function_calls:
                tool_results = await self._handle_function_calls(response)
                response = await self.provider.send_message(tool_results)
                if response.content:
                    accumulated_text += response.content
            
            # Save assistant response to history
            if self.history_manager and accumulated_text:
                self.history_manager.add_message("model", accumulated_text)
            
            logger.info(f"Message complete (sync), {len(accumulated_text)} chars")
            return accumulated_text
            
        except Exception as e:
            logger.exception("Error sending message (sync)")
            raise PoorCLIError(f"Failed to send message: {e}")

    async def execute_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any]
    ) -> str:
        """
        Execute a tool with given arguments.
        
        Args:
            tool_name: Name of the tool to execute.
            arguments: Tool arguments as a dictionary.
        
        Returns:
            Tool execution result as string.
        
        Raises:
            PoorCLIError: If not initialized or tool execution fails.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Executing tool: {tool_name}")
        
        try:
            result = await self.tool_registry.execute_tool(tool_name, arguments)
            logger.info(f"Tool {tool_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            raise PoorCLIError(f"Tool execution failed: {e}")

    def build_fim_prompt(
        self,
        code_before: str,
        code_after: str,
        instruction: str,
        file_path: str,
        language: str
    ) -> str:
        """
        Build a Fill-in-Middle (FIM) prompt for code completion.
        
        Args:
            code_before: Code before the cursor position.
            code_after: Code after the cursor position.
            instruction: Optional instruction for what to generate.
            file_path: Path to the current file.
            language: Programming language of the file.
        
        Returns:
            FIM prompt string for the AI.
        """
        import os
        filename = os.path.basename(file_path) if file_path else "unknown"
        
        # Determine provider for native FIM format selection
        provider_name = self.config.model.model_name if self.config else "generic"
        
        # Use the prompts module for consistent FIM formatting
        return _build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            filename=filename,
            language=language,
            provider=provider_name
        )

    async def inline_complete(
        self,
        code_before: str,
        code_after: str,
        instruction: str,
        file_path: str,
        language: str
    ) -> AsyncIterator[str]:
        """
        Generate inline code completion (FIM - Fill in Middle).
        
        This is the main method for Windsurf-like ghost text completion.
        
        Args:
            code_before: Code before the cursor position.
            code_after: Code after the cursor position.
            instruction: Optional instruction for what to generate.
            file_path: Path to the current file.
            language: Programming language of the file.
        
        Yields:
            Code completion chunks as they arrive.
        
        Raises:
            PoorCLIError: If not initialized or completion fails.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Inline complete for {file_path} ({language})")
        
        # Build FIM prompt
        prompt = self.build_fim_prompt(
            code_before=code_before,
            code_after=code_after,
            instruction=instruction,
            file_path=file_path,
            language=language
        )
        
        try:
            # Stream the completion
            async for chunk in self.provider.send_message_stream(prompt):
                if chunk.content:
                    yield chunk.content
            
            logger.info("Inline completion finished")
            
        except Exception as e:
            logger.exception("Error in inline completion")
            raise PoorCLIError(f"Inline completion failed: {e}")

    @property
    def permission_callback(self) -> Optional[Callable[[str, Dict], Any]]:
        """
        Get the permission callback for file operations.
        
        Returns:
            The permission callback function or None.
        """
        return self._permission_callback
    
    @permission_callback.setter
    def permission_callback(self, callback: Optional[Callable[[str, Dict], Any]]) -> None:
        """
        Set the permission callback for file operations.
        
        The callback should be an async function that takes:
            - tool_name: str - Name of the tool being executed
            - tool_args: dict - Arguments to the tool
        
        And returns:
            - bool - True to allow, False to deny
        
        Args:
            callback: The permission callback function.
        """
        self._permission_callback = callback
        logger.info("Permission callback updated")

    async def apply_edit(
        self,
        file_path: str,
        old_text: str,
        new_text: str
    ) -> str:
        """
        Apply a code edit to a file.
        
        Args:
            file_path: Path to the file to edit.
            old_text: Text to replace.
            new_text: Replacement text.
        
        Returns:
            Success or error message.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Applying edit to {file_path}")
        
        try:
            result = await self.tool_registry.execute_tool(
                "edit_file",
                {
                    "file_path": file_path,
                    "old_text": old_text,
                    "new_text": new_text
                }
            )
            return result
        except Exception as e:
            logger.error(f"Edit failed: {e}")
            return f"Error: {e}"

    async def read_file(
        self,
        file_path: str,
        start_line: Optional[int] = None,
        end_line: Optional[int] = None
    ) -> str:
        """
        Read file contents.
        
        Args:
            file_path: Path to the file to read.
            start_line: Optional start line (1-indexed).
            end_line: Optional end line (1-indexed).
        
        Returns:
            File contents as string.
        
        Raises:
            PoorCLIError: If not initialized or file read fails.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Reading file: {file_path}")
        
        try:
            args = {"file_path": file_path}
            if start_line is not None:
                args["start_line"] = start_line
            if end_line is not None:
                args["end_line"] = end_line
            
            result = await self.tool_registry.execute_tool("read_file", args)
            return result
        except Exception as e:
            logger.error(f"File read failed: {e}")
            raise PoorCLIError(f"Failed to read file: {e}")

    async def write_file(
        self,
        file_path: str,
        content: str
    ) -> str:
        """
        Write content to a file.
        
        Args:
            file_path: Path to the file to write.
            content: Content to write.
        
        Returns:
            Success message.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info(f"Writing file: {file_path}")
        
        try:
            result = await self.tool_registry.execute_tool(
                "write_file",
                {
                    "file_path": file_path,
                    "content": content
                }
            )
            return result
        except Exception as e:
            logger.error(f"File write failed: {e}")
            raise PoorCLIError(f"Failed to write file: {e}")

    def get_available_tools(self) -> List[Dict[str, Any]]:
        """
        Get list of available tools.
        
        Returns:
            List of tool declarations.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.tool_registry:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        return self.tool_registry.get_tool_declarations()

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get information about the current provider.
        
        Returns:
            Dict with keys: name, model, capabilities.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider or not self.config:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        capabilities = {}
        if hasattr(self.provider, 'capabilities') and self.provider.capabilities:
            caps = self.provider.capabilities
            capabilities = {
                "streaming": caps.supports_streaming,
                "function_calling": caps.supports_function_calling,
                "vision": caps.supports_vision,
            }
        
        return {
            "name": self.config.model.provider,
            "model": self.config.model.model_name,
            "capabilities": capabilities
        }

    async def clear_history(self) -> None:
        """
        Clear conversation history.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        logger.info("Clearing history")
        
        if hasattr(self.provider, 'clear_history'):
            await self.provider.clear_history()
        
        if self.history_manager:
            self.history_manager.clear_current_session()

    def get_history(self) -> List[Dict[str, Any]]:
        """
        Get conversation history in normalized format.
        
        Returns:
            List of dicts with 'role' and 'content' keys.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized or not self.provider:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        history = []
        
        if hasattr(self.provider, 'get_history'):
            raw_history = self.provider.get_history()
            for entry in raw_history:
                if isinstance(entry, dict):
                    history.append({
                        "role": entry.get("role", "unknown"),
                        "content": entry.get("content", "")
                    })
        
        return history

    async def switch_provider(
        self,
        provider_name: str,
        model_name: Optional[str] = None
    ) -> None:
        """
        Switch to a different AI provider.
        
        Args:
            provider_name: Name of the provider to switch to.
            model_name: Optional model name. If None, uses provider default.
        
        Raises:
            ConfigurationError: If switch fails.
        """
        logger.info(f"Switching to provider: {provider_name}")
        
        # Get API key for new provider
        api_key = self._config_manager.get_api_key(provider_name)
        
        if not api_key and provider_name != "ollama":
            raise ConfigurationError(f"No API key found for provider: {provider_name}")
        
        # Determine model name
        if not model_name:
            provider_config = self.config.model.providers.get(provider_name)
            if provider_config:
                model_name = provider_config.default_model
            else:
                raise ConfigurationError(f"Unknown provider: {provider_name}")
        
        # Get provider config for additional settings
        provider_config = self._config_manager.get_provider_config(provider_name)
        extra_kwargs = {}
        if provider_config and provider_config.base_url:
            extra_kwargs["base_url"] = provider_config.base_url
        
        # Create new provider
        self.provider = ProviderFactory.create(
            provider_name=provider_name,
            api_key=api_key or "",
            model_name=model_name,
            **extra_kwargs
        )
        
        # Update config
        self.config.model.provider = provider_name
        self.config.model.model_name = model_name
        
        # Re-initialize provider with tools
        tool_declarations = self.tool_registry.get_tool_declarations()
        await self.provider.initialize(
            tools=tool_declarations,
            system_instruction=self._system_instruction
        )
        
        logger.info(f"Switched to {provider_name}/{model_name}")

    def set_system_instruction(self, instruction: str) -> None:
        """
        Update the system instruction.
        
        Note: Takes effect on next message, not retroactively.
        
        Args:
            instruction: New system instruction.
        """
        self._system_instruction = instruction
        logger.info("System instruction updated")

    async def create_checkpoint(
        self,
        file_paths: List[str],
        description: str
    ) -> Optional[str]:
        """
        Create a checkpoint for the given files.
        
        Args:
            file_paths: List of file paths to checkpoint.
            description: Description of the checkpoint.
        
        Returns:
            Checkpoint ID or None if checkpointing is disabled.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        if not self.checkpoint_manager:
            logger.warning("Checkpoint manager not enabled")
            return None
        
        logger.info(f"Creating checkpoint for {len(file_paths)} files")
        
        try:
            checkpoint_id = await self.checkpoint_manager.create_checkpoint(
                file_paths,
                description
            )
            return checkpoint_id
        except Exception as e:
            logger.error(f"Checkpoint creation failed: {e}")
            raise PoorCLIError(f"Failed to create checkpoint: {e}")

    async def restore_checkpoint(self, checkpoint_id: str) -> bool:
        """
        Restore a checkpoint.
        
        Args:
            checkpoint_id: ID of the checkpoint to restore.
        
        Returns:
            True if successful, False otherwise.
        
        Raises:
            PoorCLIError: If not initialized.
        """
        if not self._initialized:
            raise PoorCLIError("PoorCLICore not initialized. Call initialize() first.")
        
        if not self.checkpoint_manager:
            logger.warning("Checkpoint manager not enabled")
            return False
        
        logger.info(f"Restoring checkpoint: {checkpoint_id}")
        
        try:
            success = await self.checkpoint_manager.restore_checkpoint(checkpoint_id)
            return success
        except Exception as e:
            logger.error(f"Checkpoint restore failed: {e}")
            raise PoorCLIError(f"Failed to restore checkpoint: {e}")

