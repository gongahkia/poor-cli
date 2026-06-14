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

## Entry Point

```toml
[project.entry-points."poor_cli.providers"]
my_provider = "my_package.provider:MyProvider"
```

Provider entry points must return an object with `call()`.
