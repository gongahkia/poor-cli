# ADR: MCP Hosting

Status: accepted, 2026-06-15.

`poor-cli` consumes external MCP servers and exposes a stdio MCP server for selected built-in tools. HTTP and socket transports stay out of scope for this batch.

Server policy:
- Default exposed tools are read-oriented: `read_file`, `glob`, `grep`, graph tools, `web_search`, `web_fetch`, `review`, and `replay_emit`.
- Mutating tools such as `write_file`, `edit`, and `shell` are not exposed unless explicitly configured.
- Tool calls use the same `ToolDispatcher`, schemas, sandbox rules, replay store, and web policy as native runs.
- Unknown tools, schema mismatch, and denied sandbox actions return MCP tool errors.

Client policy:
- External MCP configs support `allow_tools` and `timeout_seconds`.
- Env values are expanded for subprocess launch but redacted from surfaced errors.
- Only stdio transport is supported.
