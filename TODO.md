# TODO

Authoritative product direction and task list for `poor-cli`. This file **replaces `IDEA.md`**. It supersedes the earlier "preflight router" framing as the headline, while keeping the router as a capture mechanism rather than the product hook.

Status: in progress, 2026-06-16. Owner: gongahkia.

---

## 0. How To Read This File

- Every line under a phase that begins with `- [ ]` is a discrete task.
- Phases are ordered by dependency, not by excitement. Do them top-down.
- Each phase ends with an **Acceptance / evidence gate**. Do not mark a phase done until its gate passes and the listed evidence file exists.
- `[claims-gated]` marks tasks whose output may only be described publicly once the matching evidence exists (see §12).
- `[breaking]` marks tasks that change the documented product surface or remove a command.
- This document is the product narrative. The old `WORKON`/P0–P22 checklist is implementation history, not strategy.

---

## 1. Thesis (Revised)

The durable product sentence is no longer "smart preflight router." It is:

> `poor-cli` is a **verifiable run-record for coding agents**: it captures what an agent was asked, what context and route it got, what it did, and what changed — into a content-addressed store that **replays deterministically offline**, including its own benchmark evidence.

The reframe, stated plainly:

- The **moat is not replay**, and it is **not routing**. Both exist in other tools (see §2). The moat is that **the route decision and the benchmark numbers are the same recorded, replayable substance** as the run itself. Every claim the tool makes about an agent run can be re-verified offline, with no network and no trust in the original machine.
- The **router is the capture mechanism**, not the headline. Sitting in front of `claude`/`codex` is *how runs get recorded*, not *why the tool is worth using*.
- The **local-GPU reproducible benchmark is the proof**, not a side quest. It is the hardest possible demonstration that the replay/evidence claim is real: an offline run, on local hardware, whose score can be reproduced from the checked-in record.

What this means for emphasis going forward:

- [ ] Treat "offline-deterministic replay of a complete run" as the P0 demonstrable capability.
- [ ] Treat "reproducible local-GPU benchmark whose evidence lives in the same store" as the P0 credibility anchor.
- [x] Treat the shim/router as P1 plumbing that feeds the store, explicitly demoted from "the product."
- [x] `[breaking]` Rewrite README headline from "preflight router" to the verifiable-run-record sentence above.

---

## 2. Competitive Landscape & Differentiation

This section exists so the project can be defended honestly in interviews and a YC application. Do not claim novelty that the landscape contradicts. The findings below are as of 2026-06; re-verify before any public launch (see §14, Batch F).

### 2.1 The router front-door is a solved, crowded category — do not headline it

- **Claude Code Router (`@musistudio/claude-code-router`)** — ~26k+ stars, MIT. A local proxy that sets `ANTHROPIC_BASE_URL` to itself, intercepts Claude Code requests, and routes per task type to OpenRouter/DeepSeek/Ollama/Gemini/etc. This is the most-validated version of "near-invisible router for coding agents" and occupies the exact v1 the old `IDEA.md` described.
- **`claude_n_codex_api_proxy`**, **agentgateway**, **Bifrost** — HTTP-level interception/governance for Claude Code / Codex traffic, including prompt-guard and audit logging.

Implications for our tasks:

- [x] `[breaking]` Stop describing the router as the differentiator anywhere user-facing.
- [x] Note in README that per-task routing is table stakes, and cite CCR as prior art rather than pretending to invent it.
- [x] Recognize the mechanism gap: a **PATH shim** only sees the *invocation*; a **base-URL proxy** (CCR's approach) sees the *request stream*. For anything beyond launch-time decisions we either accept the shim's limits or adopt a proxy — decide explicitly (see §5 and Open Questions §16).

### 2.2 Local replay of agent runs is also occupied — differentiate on the vertical, not the verb

- **`agent-replay` (clay-good/agent-replay)** — 100% local, SQLite-powered CLI for time-travel debugging: replay traces, diff behavioral changes, fork runs, run evals + guard/kill-switch policies. This is the closest existing project to our substrate and shares stack and several features.
- **`cagent` (Docker)** — VCR-pattern record/replay with YAML "cassettes" that strip secrets (`Authorization`, `X-Api-Key`) and commit to version control, across OpenAI/Anthropic/Google/Mistral/xAI.
- **Agent VCR** — record/replay/**diff** specifically for MCP JSON-RPC, classifying breaking changes between two recordings.

Implications for our tasks:

- [x] Do not claim "first local replay CLI." It is not.
- [x] Differentiate explicitly on the combination competitors lack: **route decision + context packet + plan/DAG + agent I/O + reproducible local-GPU benchmark evidence, all in one content-addressed store, all offline-verifiable.** Make this combination legible in the README and demo.
- [x] Adopt the proven good ideas from competitors where we lack them: secret-stripping on capture (cagent), recording-to-recording diff (Agent VCR), fork-a-run-to-test-a-fix (agent-replay). Tracked as concrete tasks in §6 and §7.

### 2.3 Reproducible benchmark infra exists, but is cloud/Ray-shaped — local-first is the wedge

- Public guidance now codifies the reproducibility discipline (pin Docker by `sha256` digest, `PYTHONHASHSEED`, `temperature=0`, weight-hash into a run manifest, pin harness version). Infra guides (Spheron), live/rolling benchmarks (SWE-bench-Live, SWE-rebench), and training harnesses (RepoForge) all assume cloud/Ray/cluster scale.
- The under-served regime: **single-developer, local-GPU, offline, reproducible-from-checked-in-record.** That is exactly where our Phase 3 work points.

Implications for our tasks:

- [ ] Position our benchmark as *local-first and reproducible-from-record*, not as a competitor to cloud-scale eval clusters.
- [ ] Adopt the standard reproducibility controls as hard requirements in the benchmark manifest (digest-pinned containers, seed control, weight hash, harness version) — see §8.

### 2.4 One-line differentiation to defend

> Other tools route (CCR) or replay (agent-replay, cagent) or benchmark (cloud harnesses). `poor-cli` makes the route decision and the benchmark evidence the *same replayable record* as the run, verifiable offline on local hardware.

- [ ] Keep this sentence current as competitors move. It is the interview answer to "how is this different from X?"

---

## 3. Primary UX (Revised)

The capture path stays familiar, but the *demonstrated value* is the verify path.

Capture (how runs get into the store):

```sh
poor-cli shims install
claude "fix the failing parser tests"
codex exec "review the staged diff"
```

Value (why anyone cares) — the verify path is now a first-class, demoed surface:

```sh
poor-cli runs
poor-cli replay <run_id> --verify          # offline, no network, re-checks event/CAS mirrors
poor-cli runs diff <run_a> <run_b>         # behavioral diff between two records
```

- [x] Make `replay --verify` the single most polished command in the tool (clear output, explicit "no network used" proof line, non-zero exit on mismatch).
- [x] Add `poor-cli runs diff` as a first-class command (new; see §7).
- [x] Keep capture quiet by default; keep verify loud and legible.
- [ ] Default behavior table (unchanged intent, retained):
  - [ ] low-risk explain/review -> pass through and record
  - [ ] normal repo edit -> add graph/context if useful, then run chosen agent
  - [ ] high-risk/security/delete/migration/payment -> ask before write-capable execution
  - [ ] missing provider/config -> explain exactly what is missing
  - [ ] interactive bare `claude`/`codex` -> pass through in v1

---

## 4. Phase Map (Dependency Order)

```text
P0  Strategy + docs realignment            (this file, README, claims gate)   <- start here
P0  Replay/evidence hardening              (the moat, make it bulletproof)
P1  Shim/router capture front-door         (feeds the store)
P1  Run diff + fork                         (competitive parity + moat extension)
P2  Local-GPU reproducible benchmark        (the proof / credibility anchor)
P2  Offline screencast                      (the demo reveal)
P3  Secondary surfaces (TUI demote, RPC/MCP, editor)
```

- [x] Do not start P1 shim work before the P0 replay gate passes. Capturing more runs into a store you cannot fully verify offline is wasted motion.

---

## 5. Shim / Router Capture Front-Door (P1)

Reframed: this is **how runs are captured**, demoted from headline. Kept opt-in, explicit, reversible.

Commands to add (absent from current help/source — confirmed greenfield):

- [x] `poor-cli shims install`
- [x] `poor-cli shims doctor`
- [x] `poor-cli shims uninstall`

Installer behavior:

- [x] Generate `claude` and `codex` wrapper scripts under `~/.poor-cli/shims/`.
- [x] Never overwrite the real `claude`/`codex` binary.
- [x] Resolve the next real binary outside the shim dir; detect and refuse recursion.
- [x] Print exact `PATH` instructions; do **not** silently edit shell rc files in v1 (see Open Q §16).
- [x] Pass through unsupported/interactive invocations unchanged.
- [x] Persist shim events into the normal run store when a run is captured.
- [x] Add tests using a temporary `PATH` and fake `claude`/`codex` binaries.

Supported v1 capture:

- [x] `claude -p "prompt"` and equivalent print/noninteractive forms.
- [x] `claude "prompt"` when the installed CLI supports prompt-as-arg on that host.
- [x] `codex exec "prompt"`.
- [x] `echo "prompt" | claude -p` only if stdin capture does not break agent behavior.

Out of scope for v1 (record the reason in docs):

- [x] No full PTY proxy for bare interactive `claude`/`codex`.
- [x] No terminal-UI replacement.
- [x] No default interception on package install.

Mechanism decision (do not skip — it is load-bearing per §2.1):

- [x] Decide and document: PATH-shim (invocation-only, simple) vs. base-URL proxy (request-stream, CCR-style, richer capture). Default to PATH-shim for v1; record the trade-off and the migration trigger that would justify a proxy.

Secret hygiene (adopt from cagent, §2.2):

- [x] On capture, strip known secret-bearing env/headers (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `Authorization`, `X-Api-Key`, etc.) before anything reaches the store.
- [x] Add a test that asserts no known secret pattern appears in any captured artifact.

**Acceptance / evidence gate (P1 shim):**

- [x] `poor-cli shims install|doctor|uninstall` exist in `--help` and pass tests on a temp-PATH fake-binary fixture.
- [x] A captured `claude -p` run and a captured `codex exec` run both produce verifiable records (P0 gate passes on them).
- [x] Secret-scan test green. Evidence: `bench/results/shim-capture-acceptance.json`.

---

## 6. Replay Substrate — The Moat (P0, harden before anything else)

Replay already works (SQLite + CAS, reconstructs state from events, verifies mirrors without network, does not re-run shell agents deterministically). This phase makes it *unimpeachable*, because every downstream claim rests on it.

The store must answer (retained from prior direction):

- [ ] What did the user ask?
- [ ] What did the router classify?
- [ ] Which backend was chosen and why?
- [ ] What context did the agent receive?
- [ ] What plan/tasks were created?
- [ ] Which tasks ran/skipped/failed/cancelled?
- [ ] What artifacts were produced?
- [ ] What changed in the repo (final `git diff` is the filesystem delta; the store is the why/how/evidence)?
- [ ] Can the run be replayed without API/network?
- [ ] Which claims are backed by checked-in evidence?

Hardening tasks:

- [x] Make `replay --verify` emit an explicit machine-checkable verdict (JSON) plus a human line, and exit non-zero on any mismatch.
- [x] Add an explicit "network was not touched" assertion to verify (e.g., run under the existing `--offline` guard and fail if any socket attempt occurs).
- [x] Document precisely what is and is not deterministic. Shell agents are not re-run deterministically — state this in docs and in verify output, do not paper over it.
- [x] Resolve the two `ResourceWarning`s in scheduler tests (open-but-unclosed resources); they undermine the "rigorous" claim.
- [x] Define a stable, versioned on-disk record schema (the `goal -> route -> context -> plan/tasks -> agent I/O -> artifacts -> verify` shape) and write it down as a spec file in `docs/`.
- [x] Add a schema-version field to records and a migration note policy, so old records remain replayable after format changes.
- [x] Add a "verify a record produced by an older schema version" test.

Secret hygiene at rest:

- [x] Confirm secrets are never written into config or artifacts (audit the store writer paths).
- [x] Add a redaction test over a synthetic run containing planted fake secrets.

**Acceptance / evidence gate (P0 replay):**

- [x] `replay --verify` is deterministic, offline, non-zero-on-mismatch, and emits JSON verdict.
- [x] Scheduler `ResourceWarning`s eliminated; full suite green (currently 208 passed / 1 skipped / 83% cov — keep at/above this).
- [x] Record schema spec committed under `docs/` and referenced from README.
- [x] Evidence: refreshed `bench/results/phase1-acceptance.json` plus a new `bench/results/replay-verify-acceptance.json`.

---

## 7. Run Diff & Fork — Competitive Parity + Moat Extension (P1)

Competitors have these; our version is differentiated by operating over the *full vertical record* (route + context + benchmark), not just trace text.

Diff (parity with Agent VCR / agent-replay, extended):

- [x] `poor-cli runs diff <run_a> <run_b>` comparing route decision, context packet, plan/DAG shape, artifacts, and repo delta.
- [x] Classify diffs as benign vs. behavior-changing (route changed, task set changed, artifact hashes changed).
- [x] `--fail-on-change` flag for CI use.
- [x] Diff output in both human and JSON form.

Fork (parity with agent-replay):

- [x] `poor-cli runs fork <run_id>` to branch a recorded run as the starting point for a fix-and-recompare loop.
- [x] Document the fork -> edit -> re-run -> diff loop as the "regression test for a non-deterministic system" workflow.

**Acceptance / evidence gate (P1 diff/fork):**

- [x] Diff correctly flags an injected route change and an injected artifact change on a fixture pair.
- [x] `--fail-on-change` returns non-zero in CI on a known-divergent fixture.
- [x] Evidence: `bench/results/run-diff-acceptance.json`.

---

## 8. Local-GPU Reproducible Benchmark — The Proof (P2, credibility anchor)

This is the hardest evidence and the strongest interview/YC artifact: an offline, local-GPU run whose score is reproducible from the checked-in record. Position as *local-first reproducible-from-record*, not a cloud-eval competitor (§2.3).

Reproducibility controls (hard requirements, from §2.3 findings):

- [ ] Pin all eval/sandbox Docker images by `sha256` digest, never by tag.
- [ ] Set and record `PYTHONHASHSEED`, `temperature=0`, `top_p=1.0` (or document why a task needs otherwise).
- [ ] Record served-model identity in the manifest: source model, served model, quantization, dtype, context length.
- [ ] Record model weight hash (md5/sha256 of checkpoint files) in `run_manifest.json`.
- [ ] Pin benchmark harness/library versions; record them in the manifest.

Benchmark definition (retained, made explicit):

- [ ] Pinned SWE-bench Lite 10-task manifest, local agent, graph mode, Qwen2.5-Coder-32B-class model, official Docker eval, replay verification per task.
- [ ] Pass threshold: at least 50% of the checked-in Anthropic baseline. Current shown target rate 0.45 — record honestly, do not round up.
- [ ] For low-VRAM hosts, quantized 32B-class evidence is acceptable **only** when the manifest records source/served/quant/dtype/context. Smaller models do not satisfy the Phase 3 target gate. `[claims-gated]`

Target-hardware readiness (the active blocker — no Linux/CUDA access on current Mac):

- [ ] Run the Linux/CUDA readiness script on real target hardware (current Mac: Darwin, no `nvidia-smi`, Docker daemon down, no vllm/sglang). `[claims-gated]`
- [ ] Verify `nvidia-smi` presence and capture its output as an artifact.
- [ ] Verify a local serving stack (vLLM/SGLang) starts and serves the pinned model.
- [ ] Run the fixed 10-task graph-mode benchmark end-to-end on target hardware and pass the per-task verifier. `[claims-gated]`
- [ ] Wire the benchmark output into the normal run store so its evidence replays like any other run (this is the differentiator — the score is a replayable record).

**Acceptance / evidence gate (P2 benchmark):**

- [ ] 10/10 tasks executed on target hardware with verifier results recorded.
- [ ] Target rate meets the ≥50%-of-baseline gate, or the gap is recorded honestly and the claim withheld. `[claims-gated]`
- [ ] Benchmark record replays offline via `replay --verify`.
- [ ] Evidence: `bench/swe_bench_lite/results/swe10-graph-<ts>/summary.json` + `run_manifest.json` with all reproducibility fields populated, and `bench/results/phase3-*.json` closeout snapshot.

---

## 9. Offline Screencast — The Demo Reveal (P2)

Reframed from "validation chore" to "the product reveal." The screencast *is* the moat made visible.

Required shots (all currently missing):

- [ ] 45–75s continuous video, non-empty.
- [ ] Visible failed internet probe (prove offline).
- [ ] `nvidia-smi` output on screen (prove local GPU).
- [ ] Graph tools visibly in use (prove context enrichment).
- [ ] `replay <run_id> --verify` passing with the "no network used" line visible (prove the moat).
- [ ] Run id and store dir on screen (prove it is a real recorded run).

Narrative order (lead with the moat, not the router):

- [ ] Open offline -> show local GPU -> run a captured agent task -> `replay --verify` passes -> show the same record produced the benchmark score. Router shown only as "this is how it got captured."

**Acceptance / evidence gate (P2 screencast):**

- [ ] Single take hits all six shots in order.
- [ ] Evidence: video file committed/linked + `bench/results/phase3-screencast-evidence.json` listing the run id, store dir, and verify verdict shown.

---

## 10. Routing Layer (Retained, Demoted)

Routing stays useful as capture-time enrichment, not as the pitch. Keep it practical.

- [x] Keep classifier labels: `explain`, `review`, `small-edit`, `multi-file-edit`, `test-fix`, `security-risk`, `data-risk`, `migration-risk`, `design-ui`, `needs-graph`, `needs-web`, `local-ok`, `local-required`, `high-cost`, `ambiguous`.
- [x] Keep route decisions: `pass-through`, `graph-enriched`, `review-lane`, `planner-reviewer`, `swarm`, `local-provider`, `fusion-review`.
- [x] Add a route preflight function: inputs = command name, args, stdin mode, cwd, env; outputs = labels, selected route, intervention reason, pass-through command.
- [x] Extend `poor-cli route explain` to cover shim-style inputs.
- [x] Always record the route decision as an artifact (it is part of the verifiable record — this is the point).
- [x] Visible-interruption policy: interrupt only on material intent change (cross-provider reroute, write-capable high-risk, budget exceed, offline blocks a network agent, missing provider). Otherwise stay quiet.
- [x] Note limitation honestly: classifier is heuristic, not learned, and is not pluggable today. Do not imply ML where there is none.

---

## 11. Graph Context (Retained, Hidden Behind Routing)

- [ ] Auto-prefer symbolic graph context when the prompt names symbols/files/imports/call-paths/multi-file behavior (stop requiring manual `--graph`).
- [ ] Fall back to grep when tree-sitter support is missing; record a graph-fallback artifact.
- [ ] Skip graph context for plain prose/review tasks.
- [ ] Keep substrate: `find_symbol`, `definition_of`, `imports_of`, `callers_of`, `subgraph`, graph-vs-grep benchmark discipline, graph-aware replay artifacts.
- [ ] Ensure graph context is captured into the record (so "what context did the agent receive?" is answerable on replay).

---

## 12. Safety, Policy & Claims (Retained, Tightened)

The wrapper must not feel like malware, and claims must stay evidence-gated.

Safety rules:

- [x] Interception is opt-in; install path explicit; uninstall explicit and tested.
- [x] Real binary path visible via `shims doctor`.
- [x] Unsupported/interactive invocations pass through.
- [x] Secrets never copied into config/artifacts (cross-ref §5, §6).
- [x] Prompts/artifacts local by default.
- [x] High-risk write tasks require confirmation unless config explicitly disables.
- [x] Offline mode fails before network-backed calls (already fail-closed — keep it).
- [x] Risk labels triggering visible confirmation by default: auth, payment, migration, delete, security, secret, SQL/data mutation, concurrency/race-sensitive edits, generated destructive shell commands.

Claims gate (enforced by release gate, §14):

- [ ] Allowed only with evidence: "records replayable artifacts" (replay gate green), "supports graph-aware context" (graph tests green), "supports local provider routes" (adapter + target-host gates green), "measured on task set X" (linked to checked-in benchmark files).
- [ ] Disallowed without evidence: competitive-superiority claims, "best"/"SOTA" claims, model-only capability inference, implying Linux/CUDA Phase 3 done before target-host evidence exists.
- [x] Add a release-gate check that scans README/docs for disallowed claim patterns and fails if evidence files are absent.

Checked-in evidence index (keep current):

- [x] `bench/results/phase1-acceptance.json` (replay baseline/fixtures).
- [ ] `bench/swe_bench_lite/results/swe10-claude-20260614T105615Z/summary.json` (Claude baseline).
- [ ] `bench/swe_bench_lite/results/swe10-graph-20260615T020703Z/summary.json` (graph mode).
- [ ] `bench/results/phase3-*.json` (readiness/closeout).

---

## 13. Secondary Surfaces (P3)

TUI — demote to inspector/debugger:

- [ ] Keep TUI for: inspect a failed/surprising run; view route decision/DAG/artifacts/review/verifier; open `PLAN.md`/`RESULT.md`/`PATCH.diff`/`REVIEW.json`/`VERIFY.json`; compare recent runs; inspect budget/provider status.
- [ ] `[breaking]` Remove TUI-first framing from all launch/demo docs. Launch leads with capture + verify, never "open the TUI."
- [ ] Keep the existing dry/yes/replay/route-set capabilities, but document the TUI as debug/audit, not daily driver.

RPC / MCP / editor:

- [ ] Keep JSON-RPC stdio server (run/inspect/status/cancel/replay) as a secondary integration surface.
- [ ] Keep MCP client + stdio server (allowlisted safe tools). No HTTP MCP/auth server in v1.
- [ ] Support: editor extension asks `poor-cli` to classify before running; headless run + structured event subscription; MCP clients inspect replay artifacts; tools query route decisions without invoking agents.
- [ ] Do not let RPC/MCP replace the CLI capture path for daily use.

---

## 14. Implementation Cut Order (Batches)

Reordered so the moat and its proof come before the front-door, per §4.

Batch A — strategy + docs (P0):

- [x] `[breaking]` Replace `IDEA.md` with this `TODO.md`.
- [x] `[breaking]` Rewrite README headline to the verifiable-run-record sentence (§1).
- [x] Add the §2 competitive-landscape section (or a condensed form) to README/docs.
- [x] Update release gate to validate this strategy doc and the §12 claims gate.

Batch B — replay hardening (P0):

- [x] Execute all §6 tasks. Gate must pass before Batch C.

Batch C — run diff + fork (P1):

- [x] Execute all §7 tasks.

Batch D — shim installer (P1):

- [x] Execute §5 installer + capture + secret-hygiene tasks.

Batch E — route-only preflight + noninteractive wrapper execution (P1):

- [x] Add route preflight function (§10) and wire `claude -p` / `codex exec` through router -> chosen backend.
- [x] Write route-decision artifact; preserve stdout/stderr/exit-code behavior; pass through unsupported invocations.

Batch F — benchmark + screencast (P2):

- [ ] Execute §8 (requires target hardware) and §9.
- [ ] Re-verify §2 competitive findings are still current before any public launch.

Batch G — dogfood + acceptance (P2):

- [ ] Dogfood `claude "inspect repo"` and `codex exec "inspect repo"` through the shim.
- [ ] Verify replay artifacts for both.
- [ ] Add docs showing install/doctor/uninstall and failure behavior.

---

## 15. Demo Direction (Revised)

Lead with the moat, not the router, not the TUI.

- [ ] 1. Offline + local GPU established on screen (`nvidia-smi`, failed internet probe).
- [ ] 2. `claude "fix the failing parser test"` runs through the shim, quietly captured with graph context.
- [ ] 3. `poor-cli runs` then `poor-cli replay <run_id> --verify` — the verify pass, offline, is the hero moment.
- [ ] 4. `poor-cli runs diff <prev> <this>` to show behavioral comparison.
- [ ] 5. Reveal that the benchmark score came from the same kind of replayable record.
- [ ] 6. Only then, optionally: `poor-cli tui --run-id <run_id>`, framed as "debug what happened," not "the thing you use."

---

## 16. Open Questions (Keep Open Until Implementation Forces A Decision)

- [x] Should `shims install` modify shell rc files or only print PATH instructions? (Default: print only.)
- [ ] Show route decisions as a compact one-line prefix on all captured runs, or only on interventions?
- [x] Should prompt capture support stdin in v1?
- [ ] Should shim artifacts live in `.poor-cli/v6` or a separate per-user global store when run outside a repo?
- [ ] Is a PTY proxy worth attempting after noninteractive shims prove useful?
- [ ] Should the short command be `poor`, `poor-cli`, or no explicit command once shims are installed?
- [ ] **New:** PATH-shim vs. base-URL proxy as the long-term capture mechanism (§2.1, §5). What concrete capture need would justify the proxy's added complexity and the "feels like malware" risk?
- [ ] **New:** Do we adopt cagent-style committable cassettes as an export format for sharing reproducible runs, or keep records internal to the store?

---

## 17. Research Notes

Feasibility docs (shim/router):

- [x] Claude Code CLI reference incl. `claude -p` print mode: https://code.claude.com/docs/en/cli-reference
- [ ] Claude Code hooks: https://code.claude.com/docs/en/hooks
- [x] OpenAI Codex noninteractive mode: https://developers.openai.com/codex/noninteractive
- [ ] Codex CLI command reference: https://developers.openai.com/codex/cli/reference

Interpretation:

- [x] Noninteractive `claude` and `codex exec` are reasonable v1 wrapper targets.
- [ ] Hooks are useful later but do not replace a front-door router.
- [x] Bare interactive sessions pass through until a PTY proxy proves worth the complexity.

Landscape sources (from the 2026-06 pivot research — re-verify before launch, §14 Batch F):

- [ ] Claude Code Router (router prior art): claudelog.com / morphllm.com / dev.to writeups.
- [ ] `agent-replay` (clay-good): github.com/clay-good/agent-replay (closest substrate competitor).
- [ ] `cagent` session recording (VCR cassettes, secret-stripping): docker.com blog.
- [ ] Agent VCR (MCP record/replay/diff): medium writeup.
- [ ] Reproducibility discipline (digest pinning, seed/weight-hash manifests): Spheron benchmarking guide.
- [ ] Local-first replay-layer rationale (data-sovereignty regime): HuggingFace "beyond logs" writeup.
