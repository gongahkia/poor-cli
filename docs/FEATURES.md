# Feature Catalog

poor-cli is now a CLI/CI agent harness. The old editor plugin surface is not part of the working product.

## Primary Surfaces

- `poor-cli exec`: one-shot prompt execution for CI, scripts, reviews, and release gates.
- `poor-cli-server`: JSON-RPC transport for automation clients.
- CLI nouns: provider, sandbox, memory, task, review, cost, MCP, workflow, and state actions.

## Harness Capabilities

- Multi-provider routing: Gemini, OpenAI, Anthropic, OpenRouter, LiteLLM, Ollama, LM Studio, llama-server, vLLM, SGLang, HF TGI, HF Local.
- Tool orchestration: filesystem, shell, git, diagnostics, review, deploy, tasks, MCP.
- Checkpoints: snapshot before file mutations and restore by id or latest.
- Sessions: save, restore, fork, and export conversations.
- Memory: repo-local durable notes, expiry, review, semantic retrieval, and reranking.
- Economy controls: frugal, balanced, quality presets with compression, routing, and savings accounting.
- Sandbox controls: filesystem, network, process, Docker, and per-tool permission rules.
- Audit log: security and policy events in repo-local storage.
- Automations: cron, filesystem-event, and slash-triggered workflows.
- Background tasks: durable runs with retry, replay, and worktree isolation.
- MCP: stdio and Streamable HTTP servers with allow/deny lists.

## Product UI Direction

- No built-in terminal chat UI.
- Native or external clients should use the JSON-RPC backend.
- `poor-cli exec` remains the scriptable CI path.
- `poor-cli server` remains the long-running client integration path.

## Suggested QA Matrix

1. `python3 -m poor_cli help`
2. `python3 -m poor_cli exec --help`
3. `python3 -m poor_cli install info`
4. `python3 -m pytest -q tests/test_product_contracts.py`
5. `python3 -m pytest -q tests/test_tool_orchestration.py`
6. `python3 -m pytest -q tests/test_server_handlers.py`
