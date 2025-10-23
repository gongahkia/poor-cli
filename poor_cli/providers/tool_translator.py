"""
Tool declaration translator for different AI providers

Converts canonical tool format to provider-specific schemas for:
- Gemini (Google)
- OpenAI
- Anthropic (Claude)
- Ollama
"""

from typing import List, Dict, Any
from enum import Enum
from ..exceptions import setup_logger

logger = setup_logger(__name__)


class ProviderType(Enum):
    """Supported provider types"""
    GEMINI = "gemini"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    CLAUDE = "claude"  # Alias for anthropic
    OLLAMA = "ollama"


class ToolTranslator:
    """Translates canonical tool format to provider-specific formats"""

    @staticmethod
    def to_gemini(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert to Gemini format (already in this format)

        Gemini schema:
        {
            "name": "tool_name",
            "description": "...",
            "parameters": {
                "type": "OBJECT",
                "properties": {...},
                "required": [...]
            }
        }

        Args:
            tools: Tools in canonical format

        Returns:
            Tools in Gemini format
        """
        # Canonical format is Gemini format
        logger.debug(f"Translating {len(tools)} tools to Gemini format")
        return tools

    @staticmethod
    def to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert to OpenAI function calling format

        OpenAI schema:
        {
            "type": "function",
            "function": {
                "name": "tool_name",
                "description": "...",
                "parameters": {
                    "type": "object",  # lowercase
                    "properties": {...},
                    "required": [...]
                }
            }
        }

        Args:
            tools: Tools in canonical format

        Returns:
            Tools in OpenAI format
        """
        openai_tools = []

        for tool in tools:
            # Convert parameter types to lowercase
            params = tool.get("parameters", {})
            converted_params = ToolTranslator._convert_types_lowercase(params)

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": converted_params
                }
            })

        logger.debug(f"Translated {len(tools)} tools to OpenAI format")
        return openai_tools

    @staticmethod
    def to_anthropic(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert to Anthropic Claude format

        Anthropic schema:
        {
            "name": "tool_name",
            "description": "...",
            "input_schema": {
                "type": "object",
                "properties": {...},
                "required": [...]
            }
        }

        Args:
            tools: Tools in canonical format

        Returns:
            Tools in Anthropic format
        """
        anthropic_tools = []

        for tool in tools:
            params = tool.get("parameters", {})
            converted_params = ToolTranslator._convert_types_lowercase(params)

            anthropic_tools.append({
                "name": tool["name"],
                "description": tool["description"],
                "input_schema": converted_params
            })

        logger.debug(f"Translated {len(tools)} tools to Anthropic format")
        return anthropic_tools

    @staticmethod
    def to_ollama(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert to Ollama format (similar to OpenAI)

        Note: Ollama function calling support varies by model.
        Uses OpenAI-compatible format.

        Args:
            tools: Tools in canonical format

        Returns:
            Tools in Ollama format
        """
        logger.debug(f"Translating {len(tools)} tools to Ollama format (OpenAI-compatible)")
        return ToolTranslator.to_openai(tools)

    @staticmethod
    def _convert_types_lowercase(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Gemini types to lowercase format

        Gemini uses uppercase types (STRING, INTEGER, OBJECT)
        OpenAI/Anthropic use lowercase (string, integer, object)

        Args:
            params: Parameters dictionary with Gemini-style types

        Returns:
            Parameters dictionary with lowercase types
        """
        result = {}

        for key, value in params.items():
            if isinstance(value, dict):
                # Recursively convert nested dicts
                result[key] = ToolTranslator._convert_types_lowercase(value)
            elif isinstance(value, list):
                # Handle lists (e.g., required fields)
                result[key] = value
            elif isinstance(value, str) and key == "type":
                # Convert type field to lowercase
                result[key] = value.lower()
            elif isinstance(value, str) and value.isupper() and len(value) > 2:
                # Likely a type string like "STRING" or "INTEGER"
                result[key] = value.lower()
            else:
                result[key] = value

        return result

    @staticmethod
    def _convert_types_uppercase(params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert lowercase types to Gemini format (uppercase)

        Args:
            params: Parameters dictionary with lowercase types

        Returns:
            Parameters dictionary with uppercase types
        """
        result = {}

        for key, value in params.items():
            if isinstance(value, dict):
                result[key] = ToolTranslator._convert_types_uppercase(value)
            elif isinstance(value, list):
                result[key] = value
            elif isinstance(value, str) and key == "type":
                result[key] = value.upper()
            else:
                result[key] = value

        return result

    @classmethod
    def translate(cls, tools: List[Dict[str, Any]], provider: ProviderType) -> List[Dict[str, Any]]:
        """
        Main translation method - dispatches to appropriate converter

        Args:
            tools: Tools in canonical format (Gemini format)
            provider: Target provider type

        Returns:
            Tools in provider-specific format

        Raises:
            ValueError: If provider is unsupported
        """
        # Handle string provider names
        if isinstance(provider, str):
            try:
                provider = ProviderType(provider.lower())
            except ValueError:
                raise ValueError(f"Unsupported provider: {provider}")

        translators = {
            ProviderType.GEMINI: cls.to_gemini,
            ProviderType.OPENAI: cls.to_openai,
            ProviderType.ANTHROPIC: cls.to_anthropic,
            ProviderType.CLAUDE: cls.to_anthropic,  # Alias
            ProviderType.OLLAMA: cls.to_ollama,
        }

        translator = translators.get(provider)
        if not translator:
            raise ValueError(f"Unsupported provider: {provider}")

        logger.info(f"Translating tools to {provider.value} format")
        return translator(tools)

    @classmethod
    def from_provider_format(cls, tools: List[Dict[str, Any]], provider: ProviderType) -> List[Dict[str, Any]]:
        """
        Convert from provider-specific format back to canonical format

        Args:
            tools: Tools in provider-specific format
            provider: Source provider type

        Returns:
            Tools in canonical format (Gemini format)
        """
        if provider == ProviderType.GEMINI:
            return tools

        elif provider in [ProviderType.OPENAI, ProviderType.OLLAMA]:
            canonical_tools = []
            for tool in tools:
                if "function" in tool:
                    func = tool["function"]
                    params = cls._convert_types_uppercase(func.get("parameters", {}))
                    canonical_tools.append({
                        "name": func["name"],
                        "description": func["description"],
                        "parameters": params
                    })
            return canonical_tools

        elif provider in [ProviderType.ANTHROPIC, ProviderType.CLAUDE]:
            canonical_tools = []
            for tool in tools:
                params = cls._convert_types_uppercase(tool.get("input_schema", {}))
                canonical_tools.append({
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": params
                })
            return canonical_tools

        else:
            raise ValueError(f"Unsupported provider: {provider}")
