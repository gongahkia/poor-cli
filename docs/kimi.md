# Kimi

Kimi uses the OpenAI-compatible chat adapter.

```sh
poor-cli provider add kimi --model kimi-k2.7-code
poor-cli route set --role executor --profile kimi --model kimi-k2.7-code
poor-cli provider doctor kimi
```

The preset uses `https://api.moonshot.ai/v1` and `MOONSHOT_API_KEY`. If no model is passed, the default is `kimi-k2.7-code`.

## Policy

- Tool calls use the same OpenAI-compatible `tools` and `tool_choice=auto` path as vLLM/SGLang.
- Long-context compaction is relaxed only when the selected profile records `capabilities.max_context_tokens >= 200000`.
- Fallback uses `routes.executor.fallback_profile` when Kimi auth, rate-limit, tool, or context errors occur.
- Pricing is estimated only when provider usage or configured/built-in Kimi pricing is available.

## Example

```toml
[providers.kimi]
kind = "kimi"
base_url = "https://api.moonshot.ai/v1"
models = ["kimi-k2.7-code"]
auth = { env = "MOONSHOT_API_KEY" }
capabilities = { tools = true, structured_outputs = true, max_context_tokens = 256000 }

[routes.executor]
profile = "kimi"
model = "kimi-k2.7-code"
fallback_profile = "local"
```
