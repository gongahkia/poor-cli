# PRD 025: Streaming tool output with backpressure

- **Wave:** 2
- **Status:** ready
- **Owner (human):** @gongahkia
- **Estimated effort:** large (2w)
- **Blocks:** 015 (makes it truly live)
- **Blocked by:** 019
- **Files it mutates:**
  - `poor_cli/tools_async.py`
  - `poor_cli/tool_dispatch.py` (new from PRD 017)
  - `poor_cli/server/handlers/tools.py` (new from PRD 019)
- **New files it adds:**
  - `poor_cli/tool_stream.py`
  - `tests/test_tool_stream.py`

## 1. Problem

Tools today produce all output, then the result enters context. A 10K-line `cargo test` failure blocks both the server and the user. LEARNING.md §2.1: "No tool output streaming. Stream with backpressure; let the model cancel if it sees enough."

## 2. Current state

Tools return `ToolResult(output: str)` after full execution.

## 3. Goal & non-goals

**Goal:** long-running tools (bash, run_tests, process_logs) stream output chunks to the server pubsub; the server forwards to the Lua client; the Lua agent timeline renders progressively. The model sees the completed output at end-of-tool (or a summarized head if over size budget).

**Non-goals:**
- Do not stream every tool (only those that can produce large or slow output).
- Do not stream to the LLM mid-call.

## 4. Design

### 4.1 Streaming contract

```python
class StreamingToolResult(AsyncIterator[str]):
    async def __aiter__(self) -> AsyncIterator[str]: ...
    async def final(self) -> ToolResult: ...
```

Tools that can stream implement both the synchronous `call()` and a new `stream_call()`.

### 4.2 Backpressure

Consumer (the Lua client) flow-controls via RPC:

- Server buffers ≤ N chunks (default 16) per tool.
- If buffer full, server awaits consumer ack.
- Consumer calls `poor-cli/toolStreamAck` with `{eventId, chunksProcessed}`.

### 4.3 Cancellation

`poor-cli/cancelTool` as per PRD 015; the streaming iterator is `aborted` and the tool process sent `SIGTERM` → `SIGKILL` after 3 s.

### 4.4 Aggregation for model context

When streaming finishes, aggregate chunks into the final output — truncated to the tool's configured context-size budget. Never feed streaming partials directly to the model to avoid oscillating behavior.

## 5. Files to create / modify / delete

**Create**
- `poor_cli/tool_stream.py`
- `tests/test_tool_stream.py`

**Modify**
- `poor_cli/tools_async.py` — add `stream_call` on bash, run_tests, process_logs.
- `poor_cli/tool_dispatch.py` — route streaming tools through the stream path.
- `poor_cli/server/handlers/tools.py` — push chunks; handle ack.

## 6. Implementation plan

1. Land `tool_stream.py` (abstract + utilities).
2. Add `stream_call` on the three chattiest tools.
3. Wire dispatch + server.
4. Tests with synthetic slow process.
5. Integration test with `yes | head -n 10000`.
6. `make lint && make test`.

## 7. Testing & acceptance criteria

- `test_stream_produces_chunks`
- `test_backpressure_blocks_when_unacked`
- `test_cancel_kills_subprocess`
- `test_final_aggregation_truncated_to_budget`

**Done criterion**
- [ ] Streaming works end-to-end for bash.
- [ ] Backpressure verified.
- [ ] Cancel path kills subprocess.

## 8. Rollback / risk

Medium. Streaming introduces asynchrony bugs. Mitigate via explicit backpressure tests.

## 9. Out-of-scope & boundary

- 🚫 Do not stream to LLM mid-call.
- 🚫 Do not stream all tools (file_read etc. return fast).

## 10. Related PRDs & references

- PRD 015 depends on this for liveness.
- LEARNING.md §2.1.
