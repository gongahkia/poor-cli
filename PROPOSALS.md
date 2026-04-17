# poor-cli proposals — index

Working docs for agent-harness improvements. Committed so any independent
Claude Code session can pick one up and execute without prior context.

| Doc | Status | Focus |
|---|---|---|
| ~~PROPOSAL-D-DISCOVERY.md~~ | **Delivered** | `meta.*` self-discovery tools — shipped `65c8514`..`9e0c0ff` |
| [PROPOSAL-E-FRUGALITY.md](./PROPOSAL-E-FRUGALITY.md) | Ready to build | In-session memoization, result truncation, manifest stability, lazy manifest |
| [PROPOSAL-F-ROBUSTNESS.md](./PROPOSAL-F-ROBUSTNESS.md) | Ready to build | Circuit breaker, idempotency keys, auto-checkpoint, per-tool rate limits |
| [PROPOSAL-G-FUTURES.md](./PROPOSAL-G-FUTURES.md) | Reference | Deferred ideas + rejected anti-patterns + watch list |

Each doc is self-contained: philosophy, scope fences, design, files touched,
tests, acceptance criteria. Pick one, skim §1 (philosophy) + §2 (anti-scope),
then implement against §3 (end state).

## Ordering guidance

D and E are mostly independent — can land in parallel. F is also independent
but benefits from D's `meta.*` surface (so circuit / rate-limit state can be
exposed via `meta.health`). Practical order:

1. **D** first (smallest, unblocks agent discovery)
2. **E** (or **F**) next
3. The other of E/F
4. Anything from G that cleared the watch list in §4

## Philosophical invariants (apply to every proposal)

Re-read these before adding any feature:

- **Agent-centric.** User talks to agent; agent drives tools. Never a
  user-facing launcher for what should be a tool call.
- **Token-frugal.** Every unnecessary token is a bug. Every feature must
  show positive or neutral token impact on the happy path.
- **Atomic, composable tools.** Small, single-purpose, predictable. No
  LLM-inside-a-tool surprises.
- **Correctness over savings.** A cache that serves stale data isn't
  saving anything — the agent's recovery cost exceeds the save.
- **No scope sprawl.** If it looks like a plugin aggregator or a UI
  framework, it's out.

## Prior phases (for context)

| Phase | Commit | Delivered |
|---|---|---|
| A — command surface collapse | `6742fa0` | 30 `:PoorCLI*` nouns → 9 headers |
| B — tools flow through agent | `22d5918` | 31 tools + 6 Lua bridges + capability negotiation |
| C — harness hardening (T1–T12) | `9e7dc03` | Schema validation, parallel dispatch, streaming, retry, composition, health, permissions |
| Nudge — `.gitignore` safety | `7821afe` | First-run prompt to ignore `.poor-cli/` |
