from __future__ import annotations

import importlib
import json
import urllib.request
from typing import Any

from .offline import require_online
from .provider_events import ToolSchema
from .providers import ProviderRequest, ProviderResponse


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, client: Any | None = None):
        if client is None:
            client = importlib.import_module("anthropic").Anthropic()
        self.client = client

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("anthropic provider")
        kwargs = dict(request.params)
        function_tools = kwargs.pop("function_tools", None)
        create_args: dict[str, Any] = {
            "model": request.model,
            "messages": request.messages or [{"role": "user", "content": request.prompt}],
            "max_tokens": int(kwargs.pop("max_tokens", 4096)),
            **kwargs,
        }
        if request.system_prompt:
            create_args["system"] = request.system_prompt
        if function_tools is not None:
            create_args["tools"] = [_anthropic_tool(tool) for tool in function_tools]
        message = self.client.messages.create(**create_args)
        return ProviderResponse(provider=self.name, model=request.model, content=_anthropic_text(message), raw=_raw(message))


class OpenAIProvider:
    name = "openai"

    def __init__(self, client: Any | None = None):
        if client is None:
            client = importlib.import_module("openai").OpenAI()
        self.client = client

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("openai provider")
        kwargs = _responses_params(request.params)
        response = self.client.responses.create(
            model=request.model,
            input=request.messages if request.messages is not None else request.prompt,
            instructions=request.system_prompt or None,
            **kwargs,
        )
        return ProviderResponse(provider=self.name, model=request.model, content=_openai_text(response), raw=_raw(response))


class GeminiProvider:
    name = "gemini"

    def __init__(self, client: Any | None = None):
        if client is None:
            client = importlib.import_module("google.genai").Client()
        self.client = client

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("gemini provider")
        kwargs = dict(request.params)
        function_tools = kwargs.pop("function_tools", None)
        config = kwargs.pop("config", None)
        if request.system_prompt:
            config = {**(config or {}), "system_instruction": request.system_prompt}
        if function_tools is not None:
            config = {**(config or {}), "tools": [{"function_declarations": [_gemini_tool(tool) for tool in function_tools]}]}
        response = self.client.models.generate_content(
            model=request.model, contents=request.messages if request.messages is not None else request.prompt, config=config, **kwargs
        )
        return ProviderResponse(provider=self.name, model=request.model, content=_gemini_text(response), raw=_raw(response))


class OllamaProvider:
    name = "ollama"

    def __init__(self, base_url: str = "http://localhost:11434", opener: Any | None = None):
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urllib.request.urlopen

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online("ollama provider")
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "system": request.system_prompt,
            "stream": False,
            "options": request.params,
        }
        http_request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.opener(http_request) as response:
            raw = json.loads(response.read().decode())
        return ProviderResponse(provider=self.name, model=request.model, content=str(raw.get("response") or ""), raw=raw)


class OpenAICompatibleChatProvider:
    name = "openai-compatible"

    def __init__(self, base_url: str, opener: Any | None = None, headers: dict[str, str] | None = None):
        self.base_url = _openai_compatible_base_url(base_url)
        self.opener = opener or urllib.request.urlopen
        self.headers = headers or {}

    def call(self, request: ProviderRequest) -> ProviderResponse:
        require_online(f"{self.name} provider")
        messages = list(request.messages) if request.messages is not None else []
        if request.messages is None and request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        if request.messages is None:
            messages.append({"role": "user", "content": request.prompt})
        payload = {"model": request.model, "messages": messages, **_chat_params(request.params)}
        http_request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json", **self.headers},
            method="POST",
        )
        with self.opener(http_request) as response:
            raw = json.loads(response.read().decode())
        return ProviderResponse(provider=self.name, model=request.model, content=_chat_completion_text(raw), raw=raw)


class VLLMProvider(OpenAICompatibleChatProvider):
    name = "vllm"

    def __init__(self, base_url: str = "http://localhost:8000", opener: Any | None = None):
        super().__init__(base_url, opener)


class SGLangProvider(OpenAICompatibleChatProvider):
    name = "sglang"

    def __init__(self, base_url: str = "http://localhost:30000", opener: Any | None = None):
        super().__init__(base_url, opener)


def json_schema_response_format(name: str, schema: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    return {"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": strict}}


def function_tool(name: str, description: str, parameters: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters, "strict": strict}}


def responses_function_tool(name: str, description: str, parameters: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    return {"type": "function", "name": name, "description": description, "parameters": parameters, "strict": strict}


def _openai_compatible_base_url(base_url: str) -> str:
    stripped = base_url.rstrip("/")
    return stripped if stripped.endswith("/v1") else f"{stripped}/v1"


def _chat_params(params: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    fusion = normalized.pop("fusion", None)
    if isinstance(fusion, dict):
        normalized.setdefault("tools", fusion.get("tools"))
        if fusion.get("tool_choice"):
            normalized["tool_choice"] = fusion["tool_choice"]
    schema = normalized.pop("json_schema", None)
    if schema is not None and "response_format" not in normalized:
        if not isinstance(schema, dict):
            raise TypeError("json_schema param must be an object")
        name = str(schema.get("name") or "structured_output")
        raw_schema = schema.get("schema")
        if not isinstance(raw_schema, dict):
            raise TypeError("json_schema.schema param must be an object")
        normalized["response_format"] = json_schema_response_format(name, raw_schema, strict=bool(schema.get("strict", True)))
    function_tools = normalized.pop("function_tools", None)
    if function_tools is not None and "tools" not in normalized:
        if not isinstance(function_tools, list):
            raise TypeError("function_tools param must be a list")
        normalized["tools"] = [_function_tool_from_param(tool) for tool in function_tools]
        normalized.setdefault("tool_choice", "auto")
    return normalized


def _responses_params(params: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(params)
    function_tools = normalized.pop("function_tools", None)
    if function_tools is not None and "tools" not in normalized:
        if not isinstance(function_tools, list):
            raise TypeError("function_tools param must be a list")
        normalized["tools"] = [_responses_tool_from_param(tool) for tool in function_tools]
        normalized.setdefault("tool_choice", "auto")
    effort = normalized.pop("reasoning_effort", None)
    if effort is not None:
        normalized["reasoning"] = {**dict(normalized.get("reasoning") or {}), "effort": effort}
    verbosity = normalized.pop("text_verbosity", None)
    if verbosity is not None:
        normalized["text"] = {**dict(normalized.get("text") or {}), "verbosity": verbosity}
    return normalized


def _function_tool_from_param(tool: Any) -> dict[str, Any]:
    spec = _tool_spec(tool)
    return function_tool(spec.name, spec.description, spec.parameters, strict=spec.strict)


def _responses_tool_from_param(tool: Any) -> dict[str, Any]:
    spec = _tool_spec(tool)
    return responses_function_tool(spec.name, spec.description, spec.parameters, strict=spec.strict)


def _anthropic_tool(tool: Any) -> dict[str, Any]:
    spec = _tool_spec(tool)
    return {"name": spec.name, "description": spec.description, "input_schema": spec.parameters}


def _gemini_tool(tool: Any) -> dict[str, Any]:
    spec = _tool_spec(tool)
    return {"name": spec.name, "description": spec.description, "parameters": spec.parameters}


def _tool_spec(tool: Any) -> ToolSchema:
    if not isinstance(tool, dict):
        raise TypeError("function tool must be an object")
    parameters = tool.get("parameters")
    if not isinstance(parameters, dict):
        raise TypeError("function tool parameters must be an object")
    return ToolSchema(
        str(tool.get("name") or ""),
        str(tool.get("description") or ""),
        parameters,
        strict=bool(tool.get("strict", True)),
    )


def _anthropic_text(message: Any) -> str:
    parts = []
    for block in getattr(message, "content", []) or []:
        if isinstance(block, dict):
            parts.append(str(block.get("text") or ""))
        else:
            parts.append(str(getattr(block, "text", "")))
    return "".join(parts)


def _openai_text(response: Any) -> str:
    output_text = getattr(response, "output_text", None)
    if output_text:
        return str(output_text)
    chunks = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            chunks.append(str(getattr(content, "text", "")))
    return "".join(chunks)


def _gemini_text(response: Any) -> str:
    text = getattr(response, "text", None)
    return str(text or "")


def _chat_completion_text(raw: dict[str, Any]) -> str:
    choices = raw.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, dict):
        return ""
    message = first.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, list):
        return "".join(str(part.get("text") or "") if isinstance(part, dict) else str(part) for part in content)
    return str(content or "")


def _raw(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        dumped = value.model_dump()
        return dumped if isinstance(dumped, dict) else {"value": dumped}
    if isinstance(value, dict):
        return value
    return {"repr": repr(value)}
