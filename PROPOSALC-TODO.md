# PROPOSAL C — Harden the Tool-Calling Core

> **Target:** `poor-cli` v6.3 / backend change with a thin Lua surface.
> **Scope:** `poor_cli/core_tool_dispatch.py`, `poor_cli/tools_async.py`, `poor_cli/tool_registry_builder.py`, `poor_cli/tool_output_filter.py`, `poor_cli/tool_success_tracker.py`, `poor_cli/permission_rules.py`, `poor_cli/cost.py`. Test surface across `tests/`.
> **Depends on:** Phase A (collapse) optional. Phase B (integrations) benefits from C landing first or in parallel — both are possible.
> **Estimated effort:** 5–7 engineer days.

---

## 1. Context

The core agent harness runs tool calls via `core_tool_dispatch.py`. Today the dispatcher:

- Accepts any args shape the model produces (no validation before call).
- Dispatches tools serially even when they're independent.
- Returns tool output as a single string blob at end of execution.
- Has no first-class timeout, retry, or partial-result handling.
- Attributes cost to "the turn" not "the tool".
- Emits per-tool success/failure as a single boolean (in `tool_success_tracker`).

As Proposal B multiplies the number and surface of tools (from ~15 to ~40+), these sharp edges compound. Every optional plugin becomes a potential failure mode. The dispatcher needs to get much more robust before carrying that weight.

## 2. End state

**Hard invariants:**
1. Every tool call passes through JSONSchema validation **before** dispatch. Invalid calls never touch handlers; they return a structured repair message to the model.
2. Independent tool calls in a single turn dispatch concurrently.
3. Long-running tools stream partial output to the model via `toolStream` notifications.
4. Every tool has a configurable timeout; timeouts produce partial results + a cancellation marker.
5. Transient failures retry with exponential backoff; retry count is visible to the model.
6. If a tool's underlying plugin/binary is missing, the handler degrades to a fallback path and labels the result with `degraded: true`.
7. Permission rules match on **structured args**, not a stringified blob.
8. Every tool call logs attributed token + wall-time cost, surfaced in the Cost panel per-tool.
9. `tool_success_tracker` tracks per-tool p50/p95 latency, success rate, and recent errors; surfaced in `:PoorCLIDiag`.
10. Tools return **typed `ContentBlock` lists**, not raw strings; UI renders `diff`, `table`, `code`, `image` blocks appropriately.
11. Tools can recursively call other tools via a lightweight primitive, without spawning a full sub-agent.
12. Tool descriptions for the model are auto-generated from `{schema, examples}` tuples — never hand-drafted prose that can rot.

## 3. Detailed improvements

### T1 — Strict JSONSchema validation before dispatch

**Motivation.** Models produce malformed tool args regularly (wrong types, missing required, extra fields). Today these reach the handler and fail with Python stack traces that leak into the model context.

**Change.**
- Depend on `jsonschema>=4`. Already a transitive dep of some providers; pin explicitly in `pyproject.toml`.
- In `poor_cli/core_tool_dispatch.py::dispatch_tool_call`, before calling the handler, run `jsonschema.validate(args, tool.schema)`. On `ValidationError`, return:
  ```python
  ToolResult(
      content=[TextBlock(
          f"Argument validation failed for tool '{tool_name}':\n"
          f"  path: {err.json_path}\n"
          f"  error: {err.message}\n"
          f"  schema_rule: {err.validator}: {err.validator_value}\n"
          f"Please re-invoke with corrected args."
      )],
      is_error=True,
      metadata={"validation_error": True, "path": err.json_path},
  )
  ```
- Short-circuit the retry loop on validation errors (no point retrying bad args with the same args).

**Files.** `poor_cli/core_tool_dispatch.py`, `poor_cli/tool_registry_builder.py` (schema attached to tool record), `pyproject.toml`.

**Tests.** `tests/test_tool_validation.py`:
- Missing required arg → validation error returned, handler never called.
- Wrong type → validation error.
- Extra arg with `additionalProperties: false` → validation error.
- Valid args → handler called, success path.

### T2 — Parallel tool dispatch

**Motivation.** Turns with N independent tool calls (e.g. "list files AND get git status") run sequentially today. Latency adds up.

**Change.**
- In `core_tool_dispatch.py::dispatch_turn`, gather tool calls by dependency graph. Today there's no declared dependency, so assume all tool calls in a single assistant message are independent unless the tool declares `{exclusive: true}` in its registration (e.g. tools that mutate repo state — `git.push`, `deploy.run` — should be `exclusive`).
- Dispatch non-exclusive tools via `asyncio.gather`; exclusive tools run serially after any non-exclusive ones in the same message complete.
- Preserve return order so the model sees results in the order it issued the calls.

**Files.** `poor_cli/core_tool_dispatch.py`, `poor_cli/tool_registry_builder.py` (add `exclusive: bool = False` to registration).

**Tests.** `tests/test_parallel_dispatch.py`:
- Two non-exclusive tools → both start within Xms of each other (measure via handler timestamps).
- One exclusive + one non-exclusive → exclusive runs after non-exclusive completes.
- Exception in one tool doesn't kill the others (each result is independent).

### T3 — Streaming tool output

**Motivation.** Long-running tools (running a test suite, compiling, deploying) emit output over seconds or minutes. Today the model only sees final output, so it can't steer mid-execution (e.g. "cancel, wrong test matcher").

**Change.**
- Tool handlers can `async yield` `ContentBlock` chunks instead of returning a single `ToolResult`.
- Dispatcher detects async-generator handlers via `inspect.isasyncgen` and emits `poor-cli/toolStream` RPC notifications as chunks arrive.
- Final chunk may include `{final: true, metadata: {...}}` to close the stream.
- Model receives streaming chunks as ephemeral context messages (provider-dependent; Anthropic, OpenAI all support tool-call streaming in varying forms).
- Frontend Timeline panel's existing `handle_chunk` path (already exists! see `timeline.lua:327`) wires to the new `toolStream`.

**Files.** `poor_cli/core_tool_dispatch.py`, `poor_cli/server/runtime.py` (RPC notification helper), `poor_cli/core_agent_loop.py` (how provider sees stream chunks).

**Tests.** `tests/test_tool_streaming.py`:
- Async-gen handler yielding 3 chunks → 3 `toolStream` notifications dispatched before turn completes.
- Synchronous handler → no `toolStream` notifications (backward compat).

### T4 — Timeout + partial result

**Motivation.** A tool that hangs (network call, runaway subprocess) blocks the turn forever today.

**Change.**
- Tool registration gains `timeout_s: float = 30.0`.
- Dispatcher wraps the handler call in `asyncio.wait_for(..., timeout=tool.timeout_s)`.
- On timeout, if the handler is a streaming generator, collect whatever chunks arrived, append `TextBlock("... [tool timed out after Xs, partial result above]")`, return as `ToolResult(is_error=True, metadata={timeout: true})`.
- If the handler is synchronous, cancel its task and return `TextBlock("tool timed out after Xs with no output")`.

**Files.** `poor_cli/core_tool_dispatch.py`, `poor_cli/tool_registry_builder.py`.

**Tests.** `tests/test_tool_timeout.py`:
- Streaming handler that sleeps forever after yielding 2 chunks → result contains the 2 chunks + timeout marker.
- Sync handler that sleeps forever → timeout marker only.
- Handler that finishes just under the deadline → no timeout.

### T5 — Retry with exponential backoff

**Motivation.** Transient failures (network blips, provider 429s) are retryable; today they fail the turn.

**Change.**
- Tool registration gains `retry_policy: RetryPolicy | None = None`.
- `RetryPolicy(max_attempts=3, base_delay=0.5, max_delay=8.0, retry_on=(TransientError,))`.
- Dispatcher catches `TransientError` subclasses, sleeps `base_delay * 2**(attempt-1)` with jitter, retries up to `max_attempts`.
- After final failure, result metadata includes `retry_attempts: int` so the model knows and can reason about flaky infrastructure.
- **Never retry on `ValidationError` (T1) or `ToolError` (non-transient).**

**Files.** `poor_cli/core_tool_dispatch.py`, new `poor_cli/tool_errors.py` (define `TransientError`, `ToolError` if not already present).

**Tests.** `tests/test_tool_retry.py`:
- Handler fails twice with `TransientError`, third time succeeds → success result with `retry_attempts: 2`.
- Handler fails 3 times → error result with `retry_attempts: 3`.
- Handler raises `ValueError` (not transient) → fails immediately, no retry.

### T6 — Graceful degradation when a plugin/binary is missing

**Motivation.** Proposal B adds tools that prefer plugins (neogit, oil, overseer) but should work without them. Today there's no framework for this.

**Change.**
- Each tool handler that has a plugin-preferred path and a CLI fallback path must explicitly declare the fallback:
  ```python
  async def handle_git_commit(ctx, args):
      if ctx.session.capabilities.plugins.get("neogit"):
          return await commit_via_neogit(ctx, args)
      return await commit_via_cli(ctx, args)  # returns ToolResult with metadata["degraded"] = "cli"
  ```
- Fallback paths set `metadata["degraded"] = <fallback_name>` on the result.
- The Timeline panel's row for a degraded call shows a `~` glyph (distinct from ✓ ok, ! error).
- No user-facing "plugin missing" warning — the tool just works.

**Files.** Each new tool handler in Proposal B; no dispatcher change except adding `session.capabilities` to the tool ctx.

**Tests.** Covered by tool-level tests in Proposal B. Add cross-cutting: `tests/test_degradation.py` asserting that with `plugins.neogit = False`, `git.commit` still returns a successful `ToolResult` with `metadata.degraded = "cli"`.

### T7 — Structured per-arg permission rules

**Motivation.** Current rule format is `{toolName: "git.push", pattern: "*main*"}` matched against `vim.inspect(args)`. Fragile, evasion-prone.

**Change.**
- Rule format evolves to:
  ```yaml
  - tool: git.push
    args_match:
      branch: { equals: "main" }
    outcome: deny
  - tool: git.push
    args_match:
      force: { equals: true }
    outcome: prompt
  ```
- `args_match` is a dict of `{arg_path: matcher}`; matchers include `{equals, contains, matches_regex, one_of, greater_than}`.
- Backward-compat: if a rule has the old `pattern` field, keep treating it as a stringified-args regex.
- Rule engine in `permission_rules.py` walks the matcher dict against the structured args dict.

**Files.** `poor_cli/permission_rules.py`, `poor_cli/policy_engine.py`, default policy files under `poor_cli/policies/`.

**Tests.** `tests/test_permission_rules.py`:
- `equals` matcher on scalar arg.
- `one_of` matcher.
- `matches_regex` matcher.
- Rule with old `pattern` still works.
- Multiple rules — first match wins.

### T8 — Tool-level cost attribution

**Motivation.** Today the Cost dashboard shows cost per turn but not per tool. If `search.hybrid` is eating 40% of tokens, users can't see that.

**Change.**
- `ToolResult.metadata` includes `{token_cost: {in: int, out: int}, wall_time_ms: int}`.
- Dispatcher accumulates into a session-wide `tool_cost_table`.
- `cost.snapshot` RPC returns `top_tools: [{name, calls, tokens_total, cost_usd, avg_wall_ms}]`.
- Cost dashboard already has a "Top tools" section (see `panels/cost_dashboard.lua::render_lines`); wire it to the new shape.

**Files.** `poor_cli/core_tool_dispatch.py`, `poor_cli/cost.py`, `poor_cli/tool_output_filter.py` (token counting already there; expose per-call).

**Tests.** `tests/test_tool_cost_attribution.py`:
- Turn with 3 tool calls → `cost.snapshot.top_tools` has 3 entries with correct counts.
- Same tool called twice → single entry with `calls: 2`.

### T9 — Tool health surface

**Motivation.** `tool_success_tracker.py` tracks success rates already. Expose them.

**Change.**
- `tool_success_tracker` gains p50/p95 latency windows + recent error samples (last 5 per tool).
- New RPC `poor-cli/toolHealth` returns per-tool `{success_rate_1h, p50_ms, p95_ms, last_errors: []}`.
- Diag dashboard gains a "Tool health" drill section. Tool that's failing >50% surfaces in the top-level summary with `⚠`.

**Files.** `poor_cli/tool_success_tracker.py`, `poor_cli/server/handlers/diag.py` (new RPC), `nvim-poor-cli/lua/poor-cli/panels/diag.lua`.

**Tests.** `tests/test_tool_health.py`:
- 10 calls to a tool, 3 fail → `success_rate_1h = 0.7`.
- Latency histogram produces correct p50 / p95.

### T10 — Tool composition (light-weight sub-tool calls)

**Motivation.** A tool like `review.pr` wants to call `git.log`, `git.diff`, `fs.read` to assemble its result. Today it either duplicates their logic or spawns a sub-agent (heavy).

**Change.**
- Tool handlers receive a `ctx.call_tool(name, args) -> ToolResult` helper.
- This dispatches through the **same** dispatcher (with permission checks, cost attribution) but without going through a new LLM call.
- Composed calls are logged in the Timeline panel nested under the parent call.
- Depth-limited (default `max_depth=3`) to prevent recursion loops.

**Files.** `poor_cli/core_tool_dispatch.py`, `poor_cli/tool_registry_builder.py` (context object).

**Tests.** `tests/test_tool_composition.py`:
- Handler A calls handler B via `ctx.call_tool("B", {})` → B's result is included in A's result.
- Recursion loop (A calls B calls A...) → dispatcher rejects at `max_depth`.

### T11 — Typed `ContentBlock` return shape

**Motivation.** Tools today return strings. UI has to parse them heuristically. Rich results (diffs, tables, images) can't render properly.

**Change.**
- Define:
  ```python
  @dataclass
  class TextBlock: kind: str = "text"; text: str
  @dataclass
  class CodeBlock: kind: str = "code"; language: str; code: str
  @dataclass
  class DiffBlock: kind: str = "diff"; file: str; before: str; after: str
  @dataclass
  class TableBlock: kind: str = "table"; columns: list[str]; rows: list[list[str]]
  @dataclass
  class FileRefBlock: kind: str = "file"; path: str; line: int | None
  @dataclass
  class ImageBlock: kind: str = "image"; media_type: str; data_base64: str

  @dataclass
  class ToolResult:
      content: list[TextBlock | CodeBlock | DiffBlock | TableBlock | FileRefBlock | ImageBlock]
      is_error: bool = False
      metadata: dict = field(default_factory=dict)
  ```
- Old string-returning handlers wrap their result in `[TextBlock(result)]` during migration.
- Frontend Timeline panel (`timeline.lua`) gains a block-aware renderer: diff blocks get DiffAdd/DiffDelete highlighting, tables render as markdown, etc.
- Provider adapters serialize blocks to the provider's tool-result format (Anthropic content blocks, OpenAI tool-result messages) preserving structure.

**Files.** New `poor_cli/tool_blocks.py`, `poor_cli/core_tool_dispatch.py`, every tool handler, `poor_cli/providers/*.py` (serialization), `nvim-poor-cli/lua/poor-cli/timeline.lua`.

**Tests.** `tests/test_tool_blocks.py`:
- Handler returns `DiffBlock` → serialized correctly into Anthropic tool-result content.
- Frontend renders a table block with aligned columns.

### T12 — Auto-generated tool descriptions

**Motivation.** Every tool has a hand-written prose description in its registration. These drift from the schema over time and consume prompt tokens.

**Change.**
- Tool registration optionally provides `examples: list[ToolExample]` where each example is `{when: str, args: dict, result_summary: str}`.
- If `description` is omitted at registration, the system prompt section for that tool is generated from `{name, schema, examples}` using a deterministic template:
  ```
  ## {name}
  {first-line of json schema description}
  
  Arguments:
  - {arg}: {type}, {required/optional}, {description from schema}
  
  Examples:
  - When {example.when}: call with {example.args}. Result: {example.result_summary}.
  ```
- Tools that already have hand-written descriptions keep them; the generator only kicks in when description is missing.

**Files.** `poor_cli/tool_prompt_gen.py` (new), `poor_cli/core_agent_loop.py` (system prompt assembly).

**Tests.** `tests/test_tool_description_gen.py`:
- Tool with only `{name, schema, examples}` → description block is deterministic and includes every schema arg.
- Tool with both `description` and `examples` → description wins.

## 4. Implementation order

Land in this order for risk isolation:

1. **T11** (typed blocks) — foundational; everything downstream uses `ToolResult`. One week.
2. **T1** (schema validation) — 1 day after T11.
3. **T5** (retry) + **T4** (timeout) — 1 day together.
4. **T2** (parallel dispatch) — 1-2 days.
5. **T6** (degradation) — lands alongside Proposal B tools.
6. **T8** (cost attribution) — 0.5 days.
7. **T9** (health tracker extension) — 0.5 days.
8. **T7** (structured perms) — 1 day.
9. **T10** (composition) — 1 day.
10. **T3** (streaming) — 2 days; most complex, most provider-specific.
11. **T12** (autogen descriptions) — 0.5 days; can land any time.

## 5. Files expected to be touched

```
poor_cli/core_tool_dispatch.py            heavy rewrite
poor_cli/tool_registry_builder.py         schema + retry + timeout + exclusive fields
poor_cli/tools_async.py                   stream support
poor_cli/tool_output_filter.py            block-aware filter
poor_cli/tool_success_tracker.py          p50/p95, error buffer
poor_cli/permission_rules.py              structured matchers
poor_cli/cost.py                          per-tool attribution
poor_cli/core_agent_loop.py               system prompt assembly, stream plumbing
poor_cli/providers/*.py                   block serialization per provider
poor_cli/tool_blocks.py                   new
poor_cli/tool_errors.py                   new
poor_cli/tool_prompt_gen.py               new
poor_cli/server/handlers/diag.py          toolHealth RPC
nvim-poor-cli/lua/poor-cli/timeline.lua   block-aware rendering
nvim-poor-cli/lua/poor-cli/panels/diag.lua tool health section
tests/test_tool_validation.py             new
tests/test_parallel_dispatch.py           new
tests/test_tool_streaming.py              new
tests/test_tool_timeout.py                new
tests/test_tool_retry.py                  new
tests/test_degradation.py                 new
tests/test_permission_rules.py            extended
tests/test_tool_cost_attribution.py       new
tests/test_tool_health.py                 new
tests/test_tool_composition.py            new
tests/test_tool_blocks.py                 new
tests/test_tool_description_gen.py        new
pyproject.toml                            pin jsonschema
```

## 6. Benchmarks (acceptance)

To prove robustness improved, measure before/after:

| Metric | Baseline | Target |
|---|---|---|
| Turn latency for a 3-tool turn (independent tools, each 200ms) | ~600ms | ~220ms (parallel) |
| Failure rate from malformed args | ~3% of turns | ~0% |
| Time to first user-visible output on a 30s tool | 30s | <500ms (streaming) |
| p95 turn duration under 5% network flake | huge tail | bounded (retry) |

Benchmark script: `tests/bench/tool_dispatch.py`. Run before starting Proposal C changes, record numbers in `docs/perf/v6.3-baseline.md`. Run again after landing and record in `docs/perf/v6.3-final.md`. Both files go in the PR description.

## 7. Known risks

| Risk | Mitigation |
|---|---|
| Provider adapters each need block-serialization updates | Land T11 adapter-by-adapter; tests catch regressions per provider. |
| Async streaming introduces deadlocks | `asyncio.wait_for` everywhere; no unbounded `await`; timeout is mandatory. |
| jsonschema dep slows import | It doesn't (it's small), but if needed, lazy-import in `core_tool_dispatch`. |
| Retry storms under provider rate limiting | `retry_policy.max_attempts` default 3, cap total wait at `max_delay * max_attempts`. |
| Permission rule format change breaks existing deployed policies | Backward-compat shim: if rule has `pattern` field, route through legacy matcher. |
| Cost attribution noisy for tools that call providers themselves (e.g. `search.hybrid` may use embeddings) | Count tokens attributable to the tool's own LLM calls; nested calls flow up through T10. |

## 8. Done when

- All 12 invariants in §2 hold.
- Every new test in §5 is green.
- Benchmark numbers meet §6 targets.
- At least 3 production tools migrated to typed blocks (`git.status`, `fs.read`, `search.hybrid`) as proof.
- `CHANGELOG.md` / release notes describe each T1–T12 and link to PRs.
