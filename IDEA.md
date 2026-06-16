# IDEA

Authoritative product direction for `poor-cli` after the pivot from "open a TUI and drive runs" to "sit one step before the user's existing coding-agent workflow."

Status: in progress, 2026-06-16. Owner: gongahkia.

## 1. Thesis

`poor-cli` should become a near-invisible preflight router for AI coding agents.

The core user action should stay familiar:

```sh
claude "fix the parser tests"
codex "review this diff"
```

After opt-in setup, `poor-cli` should sit in front of those calls, classify the prompt, enrich context when useful, choose the right backend, apply risk and budget policy, then record an auditable run. The appeal is not that users open another dashboard. The appeal is that their existing Claude/Codex/local workflow gets safer, more context-aware, and replayable with almost no extra ceremony.

The durable product sentence:

> `poor-cli` is a smart preflight/router for Claude, Codex, and local coding agents, with deterministic replay as the audit trail.

## 2. What Changed

The old roadmap was directionally useful but over-centered the TUI. The TUI is not the product hook.

Old product surface:

```text
poor-cli run ... -> inspect in TUI -> replay
```

Better product surface:

```text
claude/codex prompt -> poor-cli shim -> classify/route/context -> real agent -> replayable record
```

This is a stronger user workflow because:

- Users already type `claude` or `codex`.
- Users do not want another app open for normal work.
- The highest-leverage moment is before the agent runs, not after.
- Routing, context, and budget policy are useful only if they happen before the expensive or risky call.
- Replay/audit should be a byproduct, not a task the user has to remember.

## 3. Primary UX

The intended v1 daily-driver flow is opt-in PATH shims:

```sh
poor-cli shims install
claude "fix failing parser tests"
codex "review the staged diff"
```

The shim should:

1. Detect the real `claude` or `codex` binary.
2. Capture noninteractive prompt/args when available.
3. Classify the request.
4. Decide whether to pass through, enrich, reroute, or ask for confirmation.
5. Invoke the chosen real agent.
6. Record route decision, prompt, agent input/output, artifacts, and replay metadata.
7. Stay quiet unless risk, budget, missing config, or an explicit route override needs user attention.

Default behavior should be boring:

```text
low-risk explain/review -> pass through and record
normal repo edit -> add graph/context if useful, then run chosen agent
high-risk/security/delete/migration/payment -> ask before write-capable execution
missing provider/config -> explain exactly what is missing
interactive bare `claude` or `codex` -> pass through in v1
```

## 4. Shim Strategy

The v1 shim should be explicit and reversible:

```sh
poor-cli shims install
poor-cli shims doctor
poor-cli shims uninstall
```

Implementation target:

- Create wrapper scripts under a controlled directory such as `~/.poor-cli/shims/`.
- Tell the user exactly what to add to `PATH`.
- Never overwrite the real `claude` or `codex` binary.
- Detect recursion by resolving the next real binary outside the shim directory.
- Persist shim events into the normal run store when a run is captured.
- Pass through unsupported invocations unchanged.

Supported v1 capture:

- `claude -p "prompt"` and equivalent print/noninteractive forms.
- `claude "prompt"` if the installed CLI supports prompt-as-arg on that host.
- `codex exec "prompt"`.
- `echo "prompt" | claude -p` only if stdin capture can be done without breaking agent behavior.

Out of scope for v1:

- Full PTY proxy for bare interactive `claude`.
- Full PTY proxy for bare interactive `codex`.
- Terminal UI replacement.
- Default interception on package install.

Reason: a simple shell shim cannot reliably see prompts typed inside another interactive TUI after the real process starts. A PTY proxy can, but it is brittle and easy to make hostile to normal terminal use. The right v1 is noninteractive shims plus pass-through interactive sessions.

## 5. Routing Layer

Routing should be practical, not magical.

Inputs:

- User prompt text.
- Current working directory and repo metadata.
- Git dirty/staged state.
- Detected files, paths, languages, tests, package manifests.
- Configured provider profiles and local provider readiness.
- User budget, offline mode, risk policy, and explicit flags.

Classifier labels:

- `explain`
- `review`
- `small-edit`
- `multi-file-edit`
- `test-fix`
- `security-risk`
- `data-risk`
- `migration-risk`
- `design-ui`
- `needs-graph`
- `needs-web`
- `local-ok`
- `local-required`
- `high-cost`
- `ambiguous`

Route decisions:

- `pass-through`: call the requested real agent with minimal recording.
- `graph-enriched`: add repo graph/context packet before calling the agent.
- `review-lane`: use reviewer route instead of executor route.
- `planner-reviewer`: plan first, execute, then review/verify.
- `swarm`: split into isolated worktrees only when task graph clearly supports parallelism.
- `local-provider`: use Ollama/vLLM/SGLang when configured and appropriate.
- `fusion-review`: use Fusion only for high-risk planning/review and only under budget gate.

Visible interruption policy:

- Do not print route explanations on every call.
- Interrupt only when the route changes user intent materially, e.g. `codex` prompt is routed to Claude/local, a write-capable high-risk task is detected, configured budget would be exceeded, offline mode blocks a network-backed agent, or a required provider is missing.
- Always record the route decision in artifacts.

## 6. Replay Substrate

Replay remains the technical moat.

Manual alternatives are fine for one-off solo work:

- Read `PLAN.md`.
- Inspect `git diff`.
- Ask another agent to inspect logs.
- Manually verify claims.

`poor-cli` is useful when those checks need to become repeatable, comparable, or CI-enforced.

The store should answer:

- What did the user ask?
- What did the router classify?
- Which backend was chosen and why?
- What context did the agent receive?
- What plan/tasks were created?
- Which tasks ran, skipped, failed, or were cancelled?
- What artifacts were produced?
- What changed in the repo?
- Can the run be replayed without API/network?
- Which claims are backed by checked-in evidence?

Core record shape:

```text
goal -> route decision -> context packet -> plan/tasks -> agent input/output -> artifacts -> replay verify
```

`git diff` remains the final filesystem delta. The run store is the why/how/evidence around that delta.

## 7. Graph Context

Graph mode is still relevant, but it should be hidden behind routing instead of requiring the user to remember `--graph`.

Desired behavior:

- If the prompt names symbols, files, imports, call paths, or multi-file behavior, prefer symbolic repo graph context.
- If tree-sitter support is missing, fall back to grep and record a graph fallback artifact.
- If the task is plain prose/review and no repo context is needed, do not build graph context.

Existing substrate that remains relevant:

- `find_symbol`
- `definition_of`
- `imports_of`
- `callers_of`
- `subgraph`
- graph-vs-grep benchmark discipline
- graph-aware replay artifacts

## 8. Local GPU Direction

The Linux/CUDA local-first work remains relevant, but it should support the shim/router story.

Desired user story:

```sh
POOR_CLI_MODE=local claude "fix this bug"
```

or:

```sh
codex "fix this bug"
```

with router decision:

```text
local route selected: vLLM, Qwen2.5-Coder-32B-class model, graph context, offline replay enabled
```

Current remaining machine gates:

- Linux/CUDA readiness must run on target hardware.
- Fixed 10-task local graph-mode SWE-bench run must pass verifier.
- 60s offline local-GPU screencast must include failed internet probe, `nvidia-smi` proof, graph tools visible, replay proof, and non-empty video.

For low-VRAM target hosts, quantized Qwen2.5-Coder-32B-class evidence is acceptable only when artifacts record source model, served model, quantization, dtype, and context length. Smaller models do not satisfy the Phase 3 target gate.

## 9. TUI Role

The TUI should be demoted to inspector/debugger.

Useful TUI jobs:

- Inspect a failed or surprising run.
- View route decision, DAG, artifacts, review, and verifier status.
- Open `PLAN.md`, `RESULT.md`, `PATCH.diff`, `REVIEW.json`, and `VERIFY.json`.
- Compare recent runs.
- Inspect budget and provider status.

Not useful as primary UX:

- Asking users to open `poor-cli tui` before normal work.
- Making users type workflow commands into a second interface.
- Treating a dashboard as the product hook.

The TUI can stay, but launch/demo should lead with invisible shim/router behavior.

## 10. RPC, MCP, and Editor Integration

RPC/MCP remain relevant as secondary integration surfaces.

Use cases:

- Editor extension asks `poor-cli` to classify a prompt before running an agent.
- Headless process starts a run and subscribes to structured events.
- MCP clients inspect replay artifacts or call safe tools.
- Other tools query route decisions without invoking agents.

This supports future integrations, but it should not replace the CLI shim path for daily use.

## 11. Safety and Policy

The wrapper must not feel like malware.

Rules:

- Interception is opt-in.
- Install path is explicit.
- Uninstall is explicit and tested.
- The real binary path is visible via `poor-cli shims doctor`.
- Unsupported or interactive invocations pass through.
- Secrets are never copied into config or artifacts.
- Prompts and artifacts are local by default.
- High-risk write tasks require confirmation unless config explicitly disables that.
- Offline mode fails before network-backed calls.
- Shell/web/MCP tools keep existing sandbox and replay boundaries.

Risk labels that should trigger visible confirmation by default:

- auth
- payment
- migration
- delete
- security
- secret
- SQL/data mutation
- concurrency/race-sensitive edits
- generated destructive shell commands

## 12. Benchmarks and Claims

Claims must stay evidence-gated.

Allowed claims:

- "records replayable artifacts" when replay gate passes.
- "supports graph-aware context" when graph tests pass.
- "supports local provider routes" when provider adapter and target-host gates pass.
- "measured on task set X" only when linked to checked-in benchmark files.

Disallowed without evidence:

- competitive superiority claims
- "best" or "state-of-the-art" style claims
- model-only capability inference
- implying Linux/CUDA Phase 3 is done before target-host evidence exists

Relevant checked-in evidence from the old plan:

- Phase 1 replay baseline and fixture evidence under `bench/results/phase1-acceptance.json`.
- Claude SWE-bench Lite 10-task result under `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z/summary.json`.
- Graph-mode SWE-bench result under `bench/swe_bench_lite/results/swe10-graph-20260615T020703Z/summary.json`.
- Phase 3 readiness/closeout snapshots under `bench/results/phase3-*.json`.

## 13. What From WORKON Still Matters

The old roadmap is no longer the product narrative. It is implementation history.

Still strategic:

- Replay store and offline verification.
- Provider profiles and route policy.
- Graph-first context.
- Review/verifier lanes.
- Worktree swarm and scheduler.
- Web tools with SSRF/cache/citation policy.
- MCP/RPC integration.
- Cost/budget ledger.
- Local Linux/CUDA setup and closeout runner.
- Benchmark and claims gates.

Not strategic as a headline:

- TUI-first usage.
- Long P0-P22 checklist.
- "Open dashboard to drive work" demo.
- Implementation-log-heavy roadmap.

Current local status:

- All tracked roadmap checklist batches are closed in the old file.
- Local Mac work is mostly cleanup/polish.
- Remaining acceptance work is target-host Linux/CUDA evidence.

## 14. Next Implementation Cut

The next product cut should be the shim/router front door.

Batch A: strategy docs and cleanup

- Replace old roadmap with this `IDEA.md`.
- Update README and launch docs to point here.
- Update release gate to validate the new strategy doc.

Batch B: shim installer

- Add `poor-cli shims install|doctor|uninstall`.
- Generate `claude` and `codex` wrapper scripts under `~/.poor-cli/shims`.
- Detect real binaries and recursion.
- Add tests using temporary PATH and fake binaries.

Batch C: route-only preflight

- Add a route preflight function that accepts command name, args, stdin mode, cwd, and env.
- Return classification labels, selected route, intervention reason, and pass-through command.
- Add `poor-cli route explain` coverage for shim-style inputs.

Batch D: noninteractive wrapper execution

- For supported `claude -p` and `codex exec`, run through router then execute the chosen backend.
- Write route decision artifact.
- Preserve stdout/stderr/exit code behavior as much as possible.
- Pass through unsupported interactive invocations.

Batch E: acceptance and dogfood

- Dogfood `claude "inspect repo"` through shim.
- Dogfood `codex exec "inspect repo"` through shim.
- Verify replay artifacts.
- Add docs showing install, doctor, uninstall, and failure behavior.

## 15. Demo Direction

New demo should not start in the TUI.

Demo script:

1. User types normal command:

   ```sh
   claude "fix the failing parser test"
   ```

2. `poor-cli` quietly classifies the prompt, sees repo edit plus graph usefulness, and enriches context.

3. Agent runs normally.

4. After completion:

   ```sh
   poor-cli runs
   poor-cli replay <run_id> --verify
   ```

5. Optional:

   ```sh
   poor-cli tui --run-id <run_id>
   ```

   This is framed as "debug/inspect what happened", not "the thing you use every day."

Phase 3 demo adds local GPU proof:

- no internet
- local Qwen2.5-Coder-32B-class route
- `nvidia-smi`
- graph context
- replay verify

## 16. Open Questions

These should stay open until implementation forces a decision:

- Whether `poor-cli shims install` should modify shell rc files or only print PATH instructions.
- Whether route decisions should be shown in a compact one-line prefix for all captured runs or only interventions.
- Whether prompt capture should support stdin in v1.
- Whether shim artifacts should live in the same `.poor-cli/v6` store or a separate per-user global store when command runs outside a repo.
- Whether a PTY proxy is worth attempting after noninteractive shims prove useful.
- Whether the short command should be `poor`, `poor-cli`, or no explicit command at all once shims are installed.

## 17. Research Notes

Primary docs checked for the shim/router feasibility:

- Claude Code CLI reference, including `claude -p "query"` print mode: https://code.claude.com/docs/en/cli-reference
- Claude Code hooks: https://code.claude.com/docs/en/hooks
- OpenAI Codex noninteractive mode: https://developers.openai.com/codex/noninteractive
- Codex CLI command reference: https://developers.openai.com/codex/cli/reference

Interpretation:

- Noninteractive `claude` and `codex exec` flows are reasonable v1 wrapper targets.
- Hooks are useful later, but they do not fully replace a front-door router.
- Bare interactive sessions should pass through until there is evidence that a PTY proxy is worth the complexity.
