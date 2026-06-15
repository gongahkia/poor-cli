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
- `messages`
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

## Budget Ledger

Provider calls are recorded in `budget/LEDGER.json` for each run. The ledger estimates tokens at roughly four UTF-8 bytes per token unless a provider response includes exact usage. If a provider reports cost directly, that value is preferred. Otherwise, configured profile pricing is used before built-in timestamped seed prices. Unknown pricing emits warnings by default; strict budget mode fails before live provider calls when pricing is unknown.

## Profiles

Provider profiles live in TOML config:

- repo: `.poor-cli/config.toml`
- user: `~/.config/poor-cli/config.toml`

CLI flags override env vars, which override repo config, user config, then built-in defaults. Config stores secret references only, for example `auth = { env = "OPENAI_API_KEY" }`; plaintext keys are rejected.

```sh
poor-cli provider add openai --model gpt-5.5
poor-cli provider add compatible --id local --base-url http://localhost:8000 --model Qwen/Qwen2.5-Coder-32B-Instruct
poor-cli provider add openrouter --model openrouter/fusion
poor-cli provider add kimi --model kimi-k2-0711-preview
poor-cli provider add ollama
poor-cli provider add vllm --base-url http://localhost:8000 --model Qwen/Qwen2.5-Coder-32B-Instruct
poor-cli provider list
poor-cli provider models
poor-cli provider doctor local
poor-cli provider switch local
poor-cli provider export local --json
poor-cli provider import profiles.json
poor-cli route explain "fix the parser"
```

OpenRouter, Kimi, Ollama, vLLM, and SGLang presets verify model discovery during `provider add` unless `--skip-verify` is set. `provider doctor` reruns the same redacted diagnostics later. Probes use OpenAI-compatible `/models` and Ollama `/api/tags`.

Default local endpoints:

- vLLM: `http://localhost:8000/v1/chat/completions`
- SGLang: `http://localhost:30000/v1/chat/completions`
- Ollama: `http://localhost:11434/api/generate`

For vLLM and SGLang, `POOR_CLI_LOCAL_BASE_URL` may be either the server origin (`http://localhost:8000`) or the OpenAI-compatible API base (`http://localhost:8000/v1`).

## Local Structured Output

For vLLM and SGLang, `ProviderRequest.params` accepts OpenAI-compatible pass-through params plus two shorthand shims:

- `json_schema`: converted to `response_format={"type":"json_schema", ...}`.
- `function_tools`: converted to `tools=[{"type":"function", ...}]` with default `tool_choice="auto"`.

OpenAI Responses requests also accept native-runner mappings for `function_tools`, `reasoning_effort`, `text_verbosity`, and `prompt_cache_key`.

## Native Runner

`ProviderBackedAgentRunner` is used for configured or local provider agents that advertise tool support. It does not replace shell runners. The loop:

- sends built-in tool schemas to the provider
- normalizes provider tool calls into one internal shape
- validates tool arguments before execution
- records provider and tool replay artifacts
- appends tool results and continues until final output or budget stop

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
