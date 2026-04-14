# Phase 20: Strategic Decisions & Product Direction

**Priority:** High — these are go/no-go gates that unblock downstream implementation PRDs.
**Estimated agents:** 4 (serialized by owner response, not by file collisions)
**Dependencies:** Agent 20C (audience) blocks 20A and 20D by design. 20B is independent.
**Philosophy:** These are **decision PRDs**, not implementation PRDs. Each agent's job is: **(a)** gather evidence from the repo, prior PRDs, and `LEARNING.md`, **(b)** draft a decision memo under the PRD's `## Outcome` section that presents options and a recommendation for the human owner, and **(c)** if the owner commits to a direction, enumerate the implementation follow-up PRDs that must be spawned. Agents must not ship code changes outside `docs/` and tiny stub edits until the owner signs off.

> **Serialization note — decision gates over file collisions.**
> These four PRDs touch mostly `docs/` files, so raw file-collision risk is low. The real serialization is **owner response latency**: 20C must resolve before 20A and 20D can pick a recommendation with confidence. Agents should draft their memos in parallel, but the "commit vs archive" recommendation in 20A and 20D must be keyed off whatever audience choice lands in 20C. If the owner is unavailable, freeze 20A/20D at the "options presented" stage — do not guess the audience.

## File scope

| Agent | Decision | Primary docs touched | Code touches (pre-decision) |
|-------|----------|----------------------|-----------------------------|
| 20A | Latent communication | `docs/LATENT_COMMUNICATION.md`, `docs/phase_20/059_outcome.md` | none (evidence gather only) |
| 20B | Rename | `docs/RENAME_DECISION.md`, `docs/phase_20/061_outcome.md` | none; rename is a full migration if (a) |
| 20C | Audience + metric | `README.md` (hook only, post-decision), `NORTH_STAR.md` (new), `docs/phase_20/062_outcome.md` | none |
| 20D | Multiplayer | `docs/MULTIPLAYER_DECISION.md`, `docs/phase_20/063_outcome.md` | none pre-decision; if (B), move code to `_experimental/` |

---

## Agent 20A: Latent Communication — Ship for Local HF or Archive

**Decision type:** 3-way (ship / archive / freeze)
**Blocked by:** 20C (audience choice clarifies whether local-model users are in scope); upstream PRD 008
**Estimated effort:** 1 day if archive/freeze; 3+ weeks if ship

### Problem

LatentMAS prototype documents 70–84% token reduction on multi-agent hops for local open-weight models. Three years of research notes; zero user-facing integration today — the in-between state is worst-of-both. Cross-ref LEARNING.md §1.5 and §4.3.

### Current state

Code complete in `poor-cli/research/latent_communication.py`; not wired to the agent loop; requires open-weight model + local GPU; API-closed providers (Anthropic, OpenAI) cannot benefit.

### DECISION REQUIRED

> - **(a) Ship for Ollama / vLLM users only.** Gate behind `ProviderCapability.LATENT_COMMUNICATION` (PRD 020). Integrate with `sub_agent.py` + `parallel_agents.py` via a `LatentChannel` for sub-agent-to-sub-agent hidden-state hand-off with text fallback if channel unavailable. Add benchmark harness on Qwen3 or Llama-4. Write user guide. 3+ weeks of work. Payoff: unique differentiator for local-model users.
> - **(b) Archive.** Delete `poor-cli/research/latent_communication.py`. Update `docs/LATENT_COMMUNICATION.md` to state "ceased." Restore-from-git escape hatch. 1 day.
> - **(c) Freeze.** Keep as research artifact; make imports raise `NotImplementedError`; update docs. 1 day.

**Recommended:** (a) if local users are a target audience (PRD 062 / Agent 20C will clarify); (b) otherwise.

### Implementation details

1. **Gather evidence.** Read `poor-cli/research/latent_communication.py` in full. Quantify the prototype's line count, test coverage, and how far it sits from `sub_agent.py` / `parallel_agents.py` integration. Cross-reference LEARNING.md §1.5 and §4.3.
2. **Map the three options** above with concrete cost/benefit.
3. **Tie recommendation to Agent 20C outcome.** If audience = (A) hobbyists or (B) researchers, prefer (a). Otherwise prefer (b). Do not recommend in absence of 20C's outcome — present both conditional branches.
4. **If (a) is chosen, list follow-ups:** provider-capability plumbing PRD, `LatentChannel` integration PRD, benchmark harness PRD, documentation PRD.
5. **If (b) is chosen, list cleanup steps:** grep for imports, remove test fixtures, update LONGTERM-TODO, note the git SHA for restoration.

### Files to create / modify

- `docs/phase_20/059_outcome.md` (new — decision memo with options, recommendation, follow-ups)
- `docs/LATENT_COMMUNICATION.md` (update to reflect final state — "shipping for local providers," "ceased," or "frozen research artifact")
- `poor-cli/research/latent_communication.py` (no changes pre-decision; post-decision either deleted, gated, or stubbed)
- `poor-cli/sub_agent.py`, `poor-cli/parallel_agents.py` (noted as integration points only if (a))

### Testing & acceptance criteria

- [ ] Evidence section quantifies current LOC, test coverage, and distance-to-integration
- [ ] All three options costed in weeks and lines-of-code delta
- [ ] Recommendation is conditional on 20C outcome (no unconditional guess)
- [ ] Follow-up PRD list drafted for the (a) branch
- [ ] Cleanup checklist drafted for the (b) branch
- [ ] Owner sign-off slot reserved at bottom of memo (`## Outcome` + date)
- [ ] No code deletion, no integration code written pre-sign-off
- If (a) ships: integration test with two Ollama sub-agents; assert token count drops
- If (b) ships: `latent_communication.py` gone; docs updated
- If (c) ships: module raises `NotImplementedError` on import

### Rollback / risk

If (a): reverting means reverting integration. If (b): restore from git SHA captured in the cleanup checklist.

### Out-of-scope & boundary

- Do not ship latent communication for closed-API providers (Anthropic, OpenAI) — the capability is fundamentally incompatible.

### Outcome (2026-04-14)

**Decision:** (a) Ship, rescoped to `hf_local`.

**Rationale:** PRD 062 chose audience (A), cost-conscious hobbyists, and says PRD 059 should ship latent communication only as local-provider cost reduction. Ollama remains unsupported because `OllamaProvider.attach_kv_cache()` documents no Ollama KV cache API, and closed providers remain unsupported. Owner follow-up accepted a local HF provider as the viable ship path because HF Transformers exposes hidden states, KV cache, and `inputs_embeds`. No access: `LEARNING.md` is absent in this checkout.

**Execution:** add `hf_local`, declare `ProviderCapability.LATENT_COMMUNICATION` only there, wire an opt-in `LatentChannel` through `sub_agent.py`, add `communication_mode` metadata/fallback in `parallel_agents.py`, prompt Neovim users who switch to `hf_local`, and keep Ollama, vLLM, llama-server, SGLang, HF TGI, LM Studio, and cloud providers on text.

---

## Agent 20B: Rename the Project — Decision

**Decision type:** 2-way (rename / keep), then (if rename) name + backward-compat strategy
**Blocked by:** none
**Estimated effort:** small if keep; 1–2 weeks migration if rename

### Problem

"poor-cli" is memorable in a HN post and a drag in an enterprise eval. The name signals "inferior" rather than "cost-aware" — an adoption ceiling flagged in LONGTERM-TODO L5 and LEARNING.md §4.3, §6.

### Current state

- pip package `poor-cli`
- GitHub repo `gongahkia/poor-cli`
- Neovim plugin `nvim-poor-cli`
- 10K+ lines of code referencing the name
- `.poor-cli/` state directory convention
- `poor-cli-server` binary

### DECISIONS REQUIRED

> **DECISION 1 — rename yes / no?**
> - (a) **Rename** — short-term migration pain; long-term adoption ceiling lifted.
> - (b) **Keep** — zero migration cost; brand risk stays.
>
> **DECISION 2 (if yes) — new name shortlist:**
> - `poor-cli` — cost-virtue named.
> - `byokit` — BYOK + toolkit.
> - `frugal` — short, unambiguous, cost-virtue.
> - `parsimony` — principle-virtue.
> - `hive` — multiplayer implication.
> - `pactcode` — BYOK agreement tone.
> - Owner-proposed: _____________
>
> **DECISION 3 (if yes) — backward-compat strategy:**
> - Ship `<newname>` AND `poor-cli` as an alias package redirecting to the new one for one major version, with deprecation warning.
> - `.poor-cli/` → `.<newname>/` auto-migration on first run, reusing the PRD 003 state-migration framework.

**Recommended:** (a) + `frugal` (short, memorable, positive-framed). With backward-compat for one release.

### Outcome (2026-04-14)

**Decision:** (b) Keep `poor-cli`.

**Rationale:** owner rejected the rename on 2026-04-14 and explicitly chose to keep the original funny name. This closes the rename question unless the owner reopens it.

**Migration plan:** no pip, GitHub, Neovim plugin, server binary, or state directory migration. Remove the temporary rename/alias work and keep `poor-cli`, `poor-cli-server`, `poor_cli`, `nvim-poor-cli`, and `.poor-cli/` as the canonical surfaces.

**Execution note:** the attempted rename has been reverted to `poor-cli`.

### Implementation details

1. **Gather evidence.** Count references via grep (`poor-cli`, `poor_cli`, `PoorCli`, `.poor-cli/`). Record the counts in the memo so the migration cost is concrete. Enumerate external surfaces: pip name, repo name, Neovim plugin directory, `poor-cli-server` binary.
2. For each shortlist candidate, note: length, positive/negative framing, collision risk (pip / GitHub / npm), trademark sniff-test.
3. **List migration follow-ups (if rename).** New repo or rename-in-place, pip alias publication, Neovim plugin rename, `poor-cli-server` → `<newname>-server`, documentation pass (~500 file touches estimated), announcement post.
4. **Do not execute rename in this agent pass.** The decision memo ends with the sign-off slot; the rename itself is its own follow-up PRD.

### Files to create / modify

- `docs/phase_20/061_outcome.md` (new — decision memo)
- `docs/RENAME_DECISION.md` (new — user-facing "we evaluated renaming; here's the outcome" doc once signed off)
- No code changes pre-decision. Post-decision rename lives in a separate implementation PRD.

### Testing & acceptance criteria

- [ ] Grep evidence: exact reference counts for each name variant
- [ ] External-surface inventory (pip, repo, Neovim, server binary, state dir)
- [ ] Shortlist table with length / framing / collision / trademark notes per candidate
- [ ] Backward-compat plan references PRD 003's migration framework
- [ ] Follow-up PRD list drafted for the rename branch
- [ ] Owner sign-off slot with both name choice and backward-compat strategy
- [ ] Zero `sed`-style rename executed in this agent pass
- Post-rename acceptance: `pip install poor-cli` prints deprecation, still works; `.poor-cli/` auto-migrated; all docs refer to new name.

### Rollback / risk

High if (a) ships. Mitigated by backward-compat alias for one release.

### Out-of-scope & boundary

- Do not rename without owner approval of both the rename decision and the specific new name.

---

## Agent 20C: Audience + North-Star Metric — Decision

**Decision type:** 3-part (primary audience / north-star metric / what gets cut)
**Blocks:** 20A (059) and 20D (063)
**Estimated effort:** small (decision doc only)

### Problem

The project is simultaneously pitched at cost-conscious hobbyists, research-minded engineers, small teams, and enterprise — four different products with no shared north-star. Marketing, docs, and roadmap implicitly span all audiences. Different feature requests pull in different directions (multiplayer is teams-ish, latent communication is research-ish, economy / BYOK is hobbyist-ish). LEARNING.md §6. This decision unblocks 20A and 20D, so it is the tentpole of Phase 20.

### DECISIONS REQUIRED

> **DECISION 1 — pick a primary audience:**
> - **(A) Cost-conscious hobbyists** — BYOK individuals, Ollama users, budget-sensitive freelancers. Matches the project name and the economy/BYOK code bias.
> - **(B) Research-minded engineers** — agent evaluators, prompt engineers, local-model enthusiasts. Matches the latent-communication prototype and provider plurality.
> - **(C) Small engineering teams** — multiplayer pair programming, shared sessions, shared history. Matches the WebRTC / RBAC / signed-invites code.
> - **(D) Enterprise** — sandboxing, audit, policy enforcement, procurement. Partial match via audit-log work.
>
> **DECISION 2 — pick a north-star metric:**
> - (i) SWE-bench Lite pass@1 (quality).
> - (ii) Median $/completion (cost).
> - (iii) Turn latency p95 (speed).
> - (iv) Contributors / month (community).
> - (v) Active sessions / week (adoption).
>
> **DECISION 3 — what gets cut if it doesn't serve the chosen audience?**
> Examples: multiplayer is (C)-only. Latent communication is (B)/(A). Deep sandbox is (D).

**Recommended:** (A) + (ii). (A) matches the name and existing code bias; (ii) is tractable and differentiates poor-cli from Claude Code / Aider / Cursor.

### Outcome (2026-04-14)

**Chosen audience:** (A) Cost-conscious hobbyists.

**Chosen north-star metric:** `median_usd_per_completion` - median estimated USD spend per completed AI coding request.

**Rationale:** the strongest shipped fit is cost control for individual BYOK/local users: multi-provider BYOK, Ollama support, economy presets, cost guardrails, cost history, savings history, and Neovim cost/savings dashboards. No access: `LEARNING.md` was referenced by this PRD but is absent in this checkout, so this outcome uses the repository evidence available here.

**Not chosen:**
- (B) Research-minded engineers: latent communication is a research prototype, not the main user loop.
- (C) Small engineering teams: multiplayer exists, but it pulls marketing and roadmap toward shared sessions instead of individual cost reduction.
- (D) Enterprise: sandbox, permissions, and audit logs exist, but procurement/policy enforcement is not the lead product.
- (i) SWE-bench Lite pass@1: keep as a trust benchmark, not the north-star.
- (iii) Turn latency p95: track as a guardrail, not the north-star.
- (iv) Contributors / month: track as project health, not the north-star.
- (v) Active sessions / week: track adoption, not the north-star.

**Feature audit:** matches are economy mode, budget templates, cost guardrails, savings dashboard, provider switching, BYOK setup, and Ollama/local-provider support. Mismatches are multiplayer-first positioning, enterprise-first trust/audit positioning, and research-first latent communication positioning.

**Downstream implications:** PRD 059 should ship latent communication only if scoped to local-provider cost reduction. PRD 063 initially pointed to cut/freeze from the audience decision; owner later overrode that on 2026-04-14 and chose (A) Commit for multiplayer.

**Follow-up issues:** #16 multiplayer commit/demo follow-up, #17 latent cost-reduction scope, #18 enterprise-first demotion.

### Implementation details

1. For each audience option, include concrete evidence from the existing codebase for fit.
2. For each metric, note measurability, reproducibility, and how well it differentiates poor-cli from competitors.
3. **Draft the README hook.** Prepare a one-sentence top-line hook conditional on each audience choice, so that on sign-off the README edit is trivial.
4. **Draft `NORTH_STAR.md` skeleton.** Include the metric, how it's measured, data source, and a placeholder for the current baseline (pull from PRD 060 once it lands).
5. **Tag PRDs with audience relevance.** In the memo, list which existing PRDs serve which audience so cuts are visible.
6. Once decided, update LONGTERM-TODO priorities (re-order around audience) and the LEARNING.md §6 answer.

### Files to create / modify

- `docs/phase_20/062_outcome.md` (new — decision memo)
- `NORTH_STAR.md` (new — skeleton; populated once decision lands)
- `README.md` (no change pre-decision; one-sentence hook update post-decision)

### Testing & acceptance criteria

- [ ] All four audiences presented with codebase-evidence for fit
- [ ] All five metrics presented with measurability/reproducibility/differentiation notes
- [ ] Explicit cut-list per audience choice
- [ ] README hook draft prepared for each audience option
- [ ] `NORTH_STAR.md` skeleton created with measurement method
- [ ] Owner sign-off slot with audience + metric + cut-list
- [ ] No silent feature cuts — any cut spawned from this decision gets its own PRD
- Post-decision: README reflects single audience; metric tracked in a reproducible way.

### Rollback / risk

None. A decision can be revised.

### Out-of-scope & boundary

- Do not silently cut features. Any cut driven by this decision needs its own implementation PRD.

---

## Agent 20D: Multiplayer — Commit or Cut

**Decision type:** 3-way (commit / cut / freeze)
**Blocked by:** 20C (audience decides whether small-team multiplayer is in scope)
**Blocks:** PRD 037
**Estimated effort:** depends on decision

### Problem

Multiplayer (WebRTC P2P with role-based RBAC and signed invites) is genuinely unique — no competitor has it. But: no demo, no UI affordance, no share-this-session button, no marketing. ~2,000 lines of WebRTC/RBAC/signed-invite code plus 500+ lines of state machine in `runtime.py`, a working server surface, minimal Neovim UI, no landing-page showcase. Current state is worst-of-both. LEARNING.md §4.5, §6.

### Current state

Working in the server; minimal UI in Neovim; no demo; no landing-page showcase.

### Outcome

**Decision:** (A) Commit.

**Owner sign-off:** 2026-04-14. Keep multiplayer and make it first-class despite PRD 062's hobbyist audience decision.

**Execution note:** PRD 037 is unblocked. The demo video remains a gating deliverable before multiplayer is treated as launch-ready marketing proof.

### DECISION REQUIRED

> - **(A) Commit.** Make multiplayer a first-class surface: chat-header "Share" button, `:PoorCLICollabQuick` invite modal wizard, Multiplayer Room panel (PRD 037), 2-minute demo video (LONGTERM-TODO M1), landing-page section. Unblocks PRD 037 and marketing spend. Size this in weeks.
> - **(B) Cut.** Move multiplayer code to `_experimental/multiplayer/` with a deprecation notice. `runtime.py` drops 500+ lines. Archive PRD 037. Size this in days.
> - **(C) Freeze.** Keep as-is; no new investment; no deprecation either. Status quo — worst option but cheapest today.

**Recommended:** depends on Agent 20C. If audience = (C) Small teams → (A). Otherwise → (B). Do not recommend unconditionally.

### Implementation details

1. **Gather evidence.** Count multiplayer LOC across the server, Neovim plugin, and `runtime.py`. Quantify cognitive cost: how many code paths in `runtime.py` exist only for multiplayer. Inventory what UI exists today vs what would be needed for a first-class surface.
2. **If (A), list follow-ups:** Share-button UI PRD, invite-flow UX PRD, demo-video LONGTERM-TODO M1 promotion, landing-page PRD, marketing content PRD.
3. **If (B), list cleanup steps:** `_experimental/multiplayer/` relocation plan, `runtime.py` simplification diff preview, PRD 037 archive note, deprecation-warning copy.
4. **No partial-commit.** Out-of-scope clause is explicit: pick one direction, do not split the difference.

### Files to create / modify

- `docs/phase_20/063_outcome.md` (new — decision memo)
- `docs/MULTIPLAYER_DECISION.md` (new — user-facing outcome doc once signed off)
- No code changes pre-decision. Post-decision the (B) branch relocates code to `_experimental/multiplayer/`; the (A) branch spawns multiple implementation PRDs.

### Testing & acceptance criteria

- [ ] Evidence section quantifies multiplayer LOC and `runtime.py` cognitive cost
- [ ] All three options costed (weeks for commit, days for cut, zero for freeze)
- [ ] Recommendation is conditional on 20C outcome
- [ ] Follow-up PRD list drafted for (A) branch
- [ ] Cleanup checklist drafted for (B) branch, with `runtime.py` line-count-delta estimate
- [ ] Explicit note: no partial-commit
- [ ] Owner sign-off slot with final direction
- [ ] No code move, no deprecation notice pushed pre-sign-off
- If (A) ships: demo recorded; invite flow user-tested.
- If (B) ships: `_experimental/multiplayer/` exists; `runtime.py` drops 500+ lines.

### Rollback / risk

(A): marketing misses. (B): bandwidth to reverse shrinks over time as the code ages in `_experimental/`.

### Out-of-scope & boundary

- Do not partial-commit. Pick a direction.
