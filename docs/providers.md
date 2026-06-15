# Providers

Providers implement one method:

```python
from poor_cli.providers import ProviderRequest, ProviderResponse


class MyProvider:
    def call(self, request: ProviderRequest) -> ProviderResponse:
        ...
```

`ProviderRequest` contains:

- `provider`
- `model`
- `prompt`
- `system_prompt`
- `params`

`ProviderResponse` contains:

- `provider`
- `model`
- `content`
- `raw`
- `cached`

## Replay Wrapper

`CachedReplayProvider` records provider requests and responses in the run store. On a matching future request, it returns the cached response and emits `provider.cache_hit`. On a miss in replay-only mode, it raises `ProviderReplayMiss`.

`CachedReplayProvider.call_many()` accepts a batch of requests, replays cached items immediately, and sends only cache misses to a wrapped provider. If the wrapped provider implements `call_many()`, misses are sent through that batch path; otherwise they fall back to individual `call()` calls.

## Built-in Adapters

The alpha includes adapters for:

- Anthropic
- OpenAI Responses
- Gemini
- Ollama
- vLLM OpenAI-compatible chat server
- SGLang OpenAI-compatible chat server

Network-backed adapters call `require_online()` before live requests, so `poor-cli --offline` fails before a network call.

Default local endpoints:

- vLLM: `http://localhost:8000/v1/chat/completions`
- SGLang: `http://localhost:30000/v1/chat/completions`
- Ollama: `http://localhost:11434/api/generate`

For vLLM and SGLang, `POOR_CLI_LOCAL_BASE_URL` may be either the server origin (`http://localhost:8000`) or the OpenAI-compatible API base (`http://localhost:8000/v1`).

## Local Structured Output

For vLLM and SGLang, `ProviderRequest.params` accepts OpenAI-compatible pass-through params plus two shorthand shims:

- `json_schema`: converted to `response_format={"type":"json_schema", ...}`.
- `function_tools`: converted to `tools=[{"type":"function", ...}]` with default `tool_choice="auto"`.

Example:

```python
ProviderRequest(
    provider="vllm",
    model="Qwen/Qwen2.5-Coder-32B-Instruct",
    prompt="Return JSON.",
    params={
        "json_schema": {
            "name": "PatchPlan",
            "schema": {
                "type": "object",
                "properties": {"files": {"type": "array", "items": {"type": "string"}}},
                "required": ["files"],
                "additionalProperties": False,
            },
        }
    },
)
```

## Entry Point

```toml
[project.entry-points."poor_cli.providers"]
my_provider = "my_package.provider:MyProvider"
```

Provider entry points must return an object with `call()`.
