# PROPOSAL G — Futures, Deferred Ideas, and Anti-Patterns

> **Target:** not shipping. This is a triage document for ideas that could be
> valuable but aren't ready to build.
> **Status:** reference doc. Update when an idea clears the bar (becomes a
> PROPOSAL-H/I/…) or is retired (moved to the anti-patterns list).

---

## 1. Why this document exists

Three risks haunt an agent harness as it matures:

1. **Feature creep.** Every clever idea gets implemented. The surface grows.
   Tokens leak. Users can't find anything.
2. **Premature optimization.** Features added before real usage data shows
   they're needed. They accumulate maintenance cost and block simpler paths.
3. **Lost context.** Ideas get proposed, debated, and half-implemented, then
   someone new joins and has to re-decide everything.

PROPOSAL-G fixes (3) by capturing the idea + the decision to defer + the
current understanding of tradeoffs. If we eventually build the thing, we build
it with prior art; if we don't, the next contributor doesn't have to
re-litigate.

**Philosophical bearings from prior proposals:**

- Agent-centric (user talks to agent; agent drives tools)
- Token-frugal (every token saved counts)
- Atomic composition (tools are small, composable, pure where possible)
- No dashboards-for-the-sake-of-dashboards
- No plugin aggregation (not a launcher for other plugins)
- Correctness over savings

Any idea below is measured against those four axes.

---

## 2. Ideas flagged DEFERRED (could ship later)

### G1 — Persistent cross-session tool-call cache

**Sketch:** write `tool_cache` (PROPOSAL-E1) contents to disk (SQLite or a
simple JSONL + index). On session start, warm the cache.

**Why it's interesting:**
- The "what's the current git status" answer often hasn't changed between
  the last session and this one.
- Reading a file you read last session shouldn't cost tokens if the mtime
  matches.

**Why it's deferred:**
- Invalidation is a minefield. Git state changes outside poor-cli. File
  mtimes are unreliable on some filesystems. Network-mounted repos do
  weird things. The failure mode (stale data → agent acts on wrong state)
  is much worse than the benefit (a few saved tokens).
- In-session memoization (E1) already captures the high-frequency cases.
- If we ever build this, it should be per-workspace, mtime-aware,
  cryptographically keyed on exact args, and opt-in via config. Not a
  default.

**Re-evaluate when:** PROPOSAL-E1 is deployed and telemetry shows which
tools dominate session token spend.

### G2 — LLM-based tool-result summarization

**Sketch:** tools that produce large results (diffs, logs) pass the content
through a small/cheap LLM call to generate a summary. Only the summary
goes to the main agent.

**Why it's interesting:**
- Could dramatically shrink tokens per turn on heavy-tool turns.
- "Spent 50k tokens worth of `git diff`; summarized to 200 tokens the
  agent needs to understand the change."

**Why it's deferred:**
- Spends tokens to save tokens. Unclear net outcome without measurement.
- Summary quality matters enormously. A wrong summary = wrong agent
  decisions = token spent on recovery.
- Correctness vs. savings tradeoff tilts against it for mutation-adjacent
  tools.
- PROPOSAL-E2 (middle-out truncation + tool_blob.get) covers the pragmatic
  case: send what fits, give the agent a handle to fetch more.

**Re-evaluate when:** we have a cheap+reliable summarization model
(cloud or local) and concrete tool-output token budgets to beat.

### G3 — Semantic tool routing via embeddings

**Sketch:** embed each tool's description and each user message; top-K
nearest tools get their schemas injected into the system prompt. Others
stay behind `meta.list_tools`.

**Why it's interesting:**
- As the tool count grows, the manifest dominates the system prompt.
  Semantic routing could make this scale indefinitely.

**Why it's deferred:**
- Agent-centric philosophy: the agent decides what to use, not a
  pre-filter that might hide the right tool.
- "Similarity" is a poor proxy for relevance in agent workflows. A user
  asking "commit this" might need fs.glob to find paths first — not
  semantically adjacent to "commit".
- PROPOSAL-E4 (lazy manifest opt-in) already addresses the token-bloat
  motivation with a simpler mechanism (domain summary + meta.list_tools
  on demand).
- If the agent struggles to find a tool, that's a discovery problem
  (PROPOSAL D) not a routing problem.

**Re-evaluate when:** tool count exceeds ~100 and `meta.list_tools` starts
showing up as a token-dominant first-turn call.

### G4 — Tool "playbooks" / named skills

**Sketch:** the agent (or user) saves a sequence of tool calls as a named
skill. Future invocations dispatch the whole sequence.

**Why it's interesting:**
- "Deploy dev" is always: `git.status` → `git.diff` → `deploy.run("dev")`.
  Encoding this as a playbook means the agent doesn't have to re-reason.
- Cuts tokens on repeat workflows.

**Why it's deferred:**
- Overlaps badly with existing `:PoorCLIAgent skill-*` and
  `:PoorCLIAgent workflow-*` which we KEPT after the Phase A purge.
- If we implement, it should plug into the existing skill system, not
  build a parallel one.
- The agent can already compose via `ctx.call_tool` (Phase-C T10).

**Re-evaluate when:** we have real examples of repeated 5+ tool-call
sequences that burn tokens each time. Until then, skills + workflows cover it.

### G5 — Tool-call transaction mode

**Sketch:** group multiple tool calls into a transaction. Either all
commit or all roll back.

**Why it's interesting:**
- "Refactor file A, rename symbol in file B, update import in file C" is
  logically atomic. A half-applied refactor is worse than none.

**Why it's deferred:**
- PROPOSAL-F3 (auto-checkpoint per-tool) already handles per-call rollback.
- True multi-call transactions need a coordinator with complex state.
- Git already provides a transaction surface (branch + commit). Agents
  can use feature branches explicitly.
- Starts to look like distributed consensus; out of scope.

**Re-evaluate when:** we can cite three user-reported incidents of
half-applied multi-tool changes where git/checkpoint didn't recover.

### G6 — Structured tool-result diffing for repeated reads

**Sketch:** if the agent reads a file twice in a session, the second read
returns only the delta since the first (not the whole file).

**Why it's interesting:**
- Agents often re-read files to check their edits. Second+ reads mostly
  overlap with the first.

**Why it's deferred:**
- Cache (E1) already handles identical reads (same args → cached).
- True diffing requires a canonical representation. What happens when
  encoding differs? When the file had no prior read? Many edge cases.
- The model might prefer the full file anyway (diff requires reconstruction).
- Token savings unclear without telemetry.

**Re-evaluate when:** E1 shows file-read tools dominating session token
spend, and we have a cheap diff library.

### G7 — Provenance chains in every result

**Sketch:** every `ToolResult.metadata` includes a `provenance` chain:
the tool name, args hash, upstream tool call(s), timestamp, git commit
of poor-cli, etc. Persisted for replay/debugging.

**Why it's interesting:**
- Forensics on "why did the agent do X?" becomes trivial.
- Regression-replay test fixtures fall out naturally.

**Why it's deferred:**
- Non-trivial storage volume.
- The audit log (`poor_cli/audit_log.py`) and `meta.call_history`
  (PROPOSAL D) cover the 90% case.
- Schema changes on every tool's ToolResult.

**Re-evaluate when:** we hit a real incident that would have been solved
by fuller provenance.

### G8 — Tool hot-reload

**Sketch:** edit `poor_cli/tools/foo.py`, save, the running server picks
up the new handler without restart.

**Why it's interesting:**
- Developer ergonomics during tool authoring.

**Why it's deferred:**
- Development convenience, not agent capability.
- `poor-cli-server --stdio` restart is cheap (≤ 2s).
- Dynamic reload + long-running sessions = state corruption risk.

**Re-evaluate when:** tool-author iteration speed becomes a bottleneck.

---

## 3. Ideas REJECTED (never building)

Each item here has explicit reasoning for the no. If circumstances change,
move it to §2 deferred.

### R1 — Tool marketplace / remote tool discovery

**No.** The attack surface (arbitrary code execution from a network
fetch), the supply-chain problem (who audits marketplace entries), and the
scope drift (poor-cli becomes a platform, not a CLI) all point the wrong
direction. MCP already exists for external tool integration; we have
`:PoorCLIDiag mcp` and `mcp_registry.lua`.

### R2 — Sub-agent swarms

**No.** Explicitly purged in the UX audit. Compounds token spend by N×.
Tool composition (T10) is sufficient for the single genuine use case
(one tool needs a helper call).

### R3 — Global kill-switch for all tools

**No.** Contrary to PROPOSAL-F §2. Per-tool circuit breakers (F1)
preserve functionality of healthy tools even when some are broken.

### R4 — LLM-based permission rules

**No.** Permissions must be deterministic. "Ask an LLM if this should be
allowed" is non-reproducible, expensive, and circumventable. Structured
rules (T7) + trust center are the right shape.

### R5 — Plugin autoloader / plugin manager UI

**No.** The plugin intentionally has a hard dependency set
(snacks/trouble/dap/neogit per init.lua). Users install those via their
package manager. poor-cli is not a plugin manager.

### R6 — Auto-prompt-engineering on the agent's system prompt

**No.** Self-modifying prompts are inscrutable and versioning them is
hell. The tool-prompt-gen module (T12) produces *deterministic* output
from schemas; that's the extent of "auto" we want.

### R7 — LLM-in-the-middle tool input sanitization

**No.** "Let's ask an LLM if the agent's args make sense before running
the tool." Adds cost, adds latency, adds a new failure mode, and doesn't
replace schema validation (T1). Just run the schema validator.

### R8 — Persistent conversation memory external to session

**No.** `poor-cli/memory.py` already exists. Adding a second memory layer
with different semantics is a maintenance disaster.

### R9 — Voice input / TUI rework / any new UI surface

**No.** We just purged UI surfaces in Phase A. Stay in `:PoorCLI<Verb>`
+ chat panel.

---

## 4. Active watch list (signals that unfreeze a deferred idea)

If these thresholds trip in real deployment, the corresponding deferred
idea comes back for review:

| Signal | Threshold | Reactivates |
|---|---|---|
| Manifest tokens ÷ total prompt tokens | > 30% | G3 (semantic routing), G2 (summarization) |
| Tool count | > 100 registered | G3 (semantic routing) |
| Same user-reported "agent forgot it could do X" in meta.call_history | > 5 incidents | Revisit PROPOSAL D scope |
| Repeat-read-same-file percentage | > 20% of fs.read calls | G6 (result diffing) |
| Session token spend on file-read tools | > 30% of total | G1 (persistent cache), G6 |
| Mean exclusive-tool failures recoverable by rollback | > 5% of dispatches | Expand PROPOSAL-F3 scope |
| Transitive tool dependency errors | recurring pattern | G5 (transactions) |

How we collect these signals: instrument `CallRecord` (Phase C T8),
periodically write aggregates to `poor_cli/state/telemetry.jsonl` in the
user's state dir, reviewed quarterly. (And only if the user opts in —
default is no telemetry upload, only local file.)

---

## 5. How to add to this document

When proposing a new idea:

1. State the idea in one sentence.
2. List the benefits concretely ("saves ~X tokens/turn on workflow Y").
3. List the costs (maintenance, token, correctness, scope).
4. Cite which PROPOSAL (A–F) already covers it, if any.
5. Park it in §2 (deferred) or §3 (rejected).
6. Note the signal that would reactivate it (§4).

When retiring a deferred idea:
- If shipping: create a new PROPOSAL-H doc at repo root, move the idea's
  design into it, delete from §2. Reference the new doc.
- If permanently rejecting: move to §3 with one-paragraph rationale.

---

## 6. Meta-principle

**Every addition to the agent harness must pay for itself in two ways:**

1. Measurable improvement on at least one axis (tokens saved, latency,
   correctness, ergonomics).
2. No measurable regression on the other axes.

"Useful in principle" isn't enough. Show the number.
