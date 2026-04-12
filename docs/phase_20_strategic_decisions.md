# Phase 20: Strategic Decisions & Product Direction

**Priority:** High — these are go/no-go gates that unblock downstream implementation PRDs.
**Estimated agents:** 4 (serialized by owner response, not by file collisions)
**Dependencies:** Agent 20C (audience) blocks 20A and 20D by design. 20B is independent.
**Philosophy:** These are **decision PRDs**, not implementation PRDs. Each agent's job is: **(a)** gather evidence from the repo, prior PRDs, and `LEARNING.md`, **(b)** draft a decision memo under the PRD's `## Outcome` section that presents options and a recommendation for the human owner, and **(c)** if the owner commits to a direction, enumerate the implementation follow-up PRDs that must be spawned. Agents must not ship code changes outside `docs/` and tiny stub edits until the owner signs off.

> **Serialization note — decision gates over file collisions.**
> These four PRDs touch mostly `docs/` files, so raw file-collision risk is low. The real serialization is **owner response latency**: 20C must resolve before 20A and 20D can pick a recommendation with confidence. Agents should draft their memos in parallel, but the "commit vs archive" recommendation in 20A and 20D must be keyed off whatever audience choice lands in 20C. If the owner is unavailable, freeze 20A/20D at the "options presented" stage — do not guess the audience.

## File scope

| Agent | PRD | Primary docs touched | Code touches (pre-decision) |
|-------|-----|----------------------|-----------------------------|
| 20A | 059 | `docs/LATENT_COMMUNICATION.md`, `docs/phase_20/059_outcome.md` | none (evidence gather only) |
| 20B | 061 | `docs/RENAME_DECISION.md`, `docs/phase_20/061_outcome.md` | none; rename is a full migration if (a) |
| 20C | 062 | `README.md` (hook only, post-decision), `docs/METRICS.md` (new), `docs/phase_20/062_outcome.md` | none |
| 20D | 063 | `docs/MULTIPLAYER_DECISION.md`, `docs/phase_20/063_outcome.md` | none pre-decision; if (B), move code to `_experimental/` |

---

## Agent 20A: Latent Communication — Ship for Ollama or Archive

**Decision type:** 3-way (ship / archive / freeze)
**Blocked by:** 20C (audience choice clarifies whether local-model users are in scope)
**Estimated effort:** 1 day if archive/freeze; 3+ weeks if ship

### What to build

A decision memo evaluating whether the LatentMAS prototype in `poor_cli/research/latent_communication.py` should be wired into the sub-agent loop (Ollama/vLLM only), deleted outright, or frozen as a research artifact. LatentMAS reports 70–84% token reduction on multi-agent hops for open-weight models but has zero user-facing integration today — the in-between state is the worst option.

### Implementation details

1. **Gather evidence.** Read `poor_cli/research/latent_communication.py` in full. Quantify the prototype's line count, test coverage, and how far it sits from `sub_agent.py` / `parallel_agents.py` integration. Cross-reference LEARNING.md §1.5 and §4.3.
2. **Map the three options** with concrete cost/benefit:
   - **(a) Ship for Ollama/vLLM:** gate behind `ProviderCapability.LATENT_COMMUNICATION` (see PRD 020), build `LatentChannel` for sub-agent hand-off with text fallback, add benchmark harness on Qwen3 or Llama-4, write user guide. 3+ weeks.
   - **(b) Archive:** delete `research/latent_communication.py`, restore-from-git escape hatch, update `docs/LATENT_COMMUNICATION.md` to state "ceased." 1 day.
   - **(c) Freeze:** keep as artifact, make imports raise `NotImplementedError`, update docs. 1 day.
3. **Tie recommendation to PRD 062 outcome.** If audience = (A) hobbyists or (B) researchers, prefer (a). Otherwise prefer (b). Do not recommend in absence of 20C's outcome — present both conditional branches.
4. **If (a) is chosen, list follow-ups:** provider-capability plumbing PRD, `LatentChannel` integration PRD, benchmark harness PRD, documentation PRD.
5. **If (b) is chosen, list cleanup steps:** grep for imports, remove test fixtures, update LONGTERM-TODO, note the git SHA for restoration.

### Files to create/modify

- `docs/phase_20/059_outcome.md` (new — decision memo with options, recommendation, follow-ups)
- `docs/LATENT_COMMUNICATION.md` (update to reflect final state — "shipping for local providers," "ceased," or "frozen research artifact")
- `poor_cli/research/latent_communication.py` (no changes pre-decision; post-decision either deleted, gated, or stubbed)
- `poor_cli/sub_agent.py`, `poor_cli/parallel_agents.py` (noted as integration points only if (a))

### Acceptance criteria

- [ ] Evidence section quantifies current LOC, test coverage, and distance-to-integration
- [ ] All three options costed in weeks and lines-of-code delta
- [ ] Recommendation is conditional on 20C outcome (no unconditional guess)
- [ ] Follow-up PRD list drafted for the (a) branch
- [ ] Cleanup checklist drafted for the (b) branch
- [ ] Owner sign-off slot reserved at bottom of memo (`## Outcome` + date)
- [ ] No code deletion, no integration code written pre-sign-off

**PRD reference:** prd/059-latent-communication-decision.md

---

## Agent 20B: Rename the Project — Decision

**Decision type:** 2-way (rename / keep), then (if rename) name + backward-compat strategy
**Blocked by:** none
**Estimated effort:** small if keep; 1–2 weeks migration if rename

### What to build

A decision memo weighing whether "poor-cli" should be renamed. The name is memorable at hobbyist scale but signals "inferior" in enterprise eval — an adoption ceiling flagged in LONGTERM-TODO L5 and LEARNING.md §4.3. The current codebase has ~10K lines referencing the name, a pip package, a GitHub repo, a Neovim plugin, and a `.poor-cli/` state directory convention. Rename is reversible only through backward-compat aliases.

### Implementation details

1. **Gather evidence.** Count references via grep (`poor-cli`, `poor_cli`, `PoorCli`, `.poor-cli/`). Record the counts in the memo so the migration cost is concrete. Enumerate external surfaces: pip name, repo name, Neovim plugin directory, `poor-cli-server` binary.
2. **Decision 1 — rename yes/no.** Present cost (one-time migration, alias maintenance) vs benefit (adoption ceiling lifted, positive framing).
3. **Decision 2 — new name shortlist.** Present the PRD's shortlist (`thriftcode`, `byokit`, `frugal`, `parsimony`, `hive`, `pactcode`) plus reserved row for owner-proposed name. For each, note: length, positive/negative framing, collision risk (pip / GitHub / npm), trademark sniff-test.
4. **Decision 3 — backward-compat strategy.** Describe the two-track plan: (i) pip alias `poor-cli` → `<newname>` for one major version with deprecation warning; (ii) `.poor-cli/` → `.<newname>/` auto-migration on first run, reusing the PRD 003 state-migration framework.
5. **List migration follow-ups (if rename).** New repo or rename-in-place, pip alias publication, Neovim plugin rename, `poor-cli-server` → `<newname>-server`, documentation pass (~500 file touches estimated), announcement post.
6. **Do not execute rename in this agent pass.** The decision memo ends with the sign-off slot; the rename itself is its own follow-up PRD.

### Files to create/modify

- `docs/phase_20/061_outcome.md` (new — decision memo)
- `docs/RENAME_DECISION.md` (new — user-facing "we evaluated renaming; here's the outcome" doc once signed off)
- No code changes pre-decision. Post-decision rename lives in a separate implementation PRD.

### Acceptance criteria

- [ ] Grep evidence: exact reference counts for each name variant
- [ ] External-surface inventory (pip, repo, Neovim, server binary, state dir)
- [ ] Shortlist table with length / framing / collision / trademark notes per candidate
- [ ] Backward-compat plan references PRD 003's migration framework
- [ ] Follow-up PRD list drafted for the rename branch
- [ ] Owner sign-off slot with both name choice and backward-compat strategy
- [ ] Zero `sed`-style rename executed in this agent pass

**PRD reference:** prd/061-rename-decision.md

---

## Agent 20C: Audience + North-Star Metric — Decision

**Decision type:** 3-part (primary audience / north-star metric / what gets cut)
**Blocks:** 20A (059) and 20D (063)
**Estimated effort:** small (decision doc only)

### What to build

A decision memo that picks one primary audience, one north-star metric, and lists which features get cut if they don't serve the chosen audience. The project today pitches at cost-conscious hobbyists, research-minded engineers, small teams, and enterprise — four different products with no shared north-star. This decision unblocks PRDs 059 and 063, so it is the tentpole of Phase 20.

### Implementation details

1. **Decision 1 — primary audience.** Present the four options with concrete evidence from the existing codebase:
   - **(A) Cost-conscious hobbyists** — BYOK individuals, Ollama users, budget freelancers. Matches the project name and the economy/BYOK code bias.
   - **(B) Research-minded engineers** — agent evaluators, prompt engineers, local-model enthusiasts. Matches the latent-communication prototype and provider plurality.
   - **(C) Small engineering teams** — multiplayer pair programming, shared sessions. Matches the WebRTC / RBAC / signed-invites code.
   - **(D) Enterprise** — sandboxing, audit, policy. Partial match via audit-log work.
2. **Decision 2 — north-star metric.** Present the five options and pick one:
   - (i) SWE-bench Lite pass@1 (quality)
   - (ii) Median $/completion (cost)
   - (iii) Turn latency p95 (speed)
   - (iv) Contributors / month (community)
   - (v) Active sessions / week (adoption)
   For each, note measurability, reproducibility, and how well it differentiates poor-cli from Claude Code / Aider / Cursor.
3. **Decision 3 — what gets cut.** Explicitly list features that lose investment if they don't serve the chosen audience. Example mappings: multiplayer is (C)-only; latent communication is (B)/(A); deep sandbox is (D).
4. **Draft the README hook.** Prepare a one-sentence top-line hook conditional on each audience choice, so that on sign-off the README edit is trivial.
5. **Draft `docs/METRICS.md` skeleton.** Include the metric, how it's measured, data source, and a placeholder for the current baseline (pull from PRD 060 once it lands).
6. **Tag PRDs with audience relevance.** In the memo, list which existing PRDs serve which audience so cuts are visible.

### Files to create/modify

- `docs/phase_20/062_outcome.md` (new — decision memo)
- `docs/METRICS.md` (new — skeleton; populated once decision lands)
- `README.md` (no change pre-decision; one-sentence hook update post-decision)

### Acceptance criteria

- [ ] All four audiences presented with codebase-evidence for fit
- [ ] All five metrics presented with measurability/reproducibility/differentiation notes
- [ ] Explicit cut-list per audience choice
- [ ] README hook draft prepared for each audience option
- [ ] `docs/METRICS.md` skeleton created with measurement method
- [ ] Owner sign-off slot with audience + metric + cut-list
- [ ] No silent feature cuts — any cut spawned from this decision gets its own PRD

**PRD reference:** prd/062-audience-north-star.md

---

## Agent 20D: Multiplayer — Commit or Cut

**Decision type:** 3-way (commit / cut / freeze)
**Blocked by:** 20C (audience decides whether small-team multiplayer is in scope)
**Blocks:** PRD 037
**Estimated effort:** depends on decision

### What to build

A decision memo that resolves the multiplayer limbo. Today there are ~2,000 lines of WebRTC/RBAC/signed-invite code plus 500+ lines of state machine in `runtime.py`, a working server surface, minimal Neovim UI, no demo, no "Share" button, no landing-page showcase. The current state is genuinely unique in the market but invisible to users — worst-of-both. LEARNING.md §4.5 and §6.

### Implementation details

1. **Gather evidence.** Count multiplayer LOC across the server, Neovim plugin, and `runtime.py`. Quantify cognitive cost: how many code paths in `runtime.py` exist only for multiplayer. Inventory what UI exists today vs what would be needed for first-class surface.
2. **Map the three options:**
   - **(A) Commit.** Chat-header "Share" button, `:PoorCliCollabQuick` invite modal wizard, Multiplayer Room panel (PRD 037), 2-minute demo video (LONGTERM-TODO M1), landing-page section. Unblocks PRD 037 and marketing. Size this in weeks.
   - **(B) Cut.** Move multiplayer code to `_experimental/multiplayer/` with deprecation notice. `runtime.py` drops 500+ lines. Archive PRD 037. Size this in days.
   - **(C) Freeze.** Keep as-is, no new investment, no deprecation. Status quo — the worst option but the cheapest today.
3. **Tie recommendation to PRD 062 outcome.** If audience = (C) small teams → (A). Otherwise → (B). Do not recommend unconditionally.
4. **If (A), list follow-ups:** Share-button UI PRD, invite-flow UX PRD, demo-video LONGTERM-TODO promotion, landing-page PRD, marketing content PRD.
5. **If (B), list cleanup steps:** `_experimental/multiplayer/` relocation plan, `runtime.py` simplification diff preview, PRD 037 archive note, deprecation-warning copy.
6. **No partial-commit.** The PRD's out-of-scope clause is explicit: pick one direction, do not split the difference.

### Files to create/modify

- `docs/phase_20/063_outcome.md` (new — decision memo)
- `docs/MULTIPLAYER_DECISION.md` (new — user-facing outcome doc once signed off)
- No code changes pre-decision. Post-decision the (B) branch relocates code to `_experimental/multiplayer/`; the (A) branch spawns multiple implementation PRDs.

### Acceptance criteria

- [ ] Evidence section quantifies multiplayer LOC and `runtime.py` cognitive cost
- [ ] All three options costed (weeks for commit, days for cut, zero for freeze)
- [ ] Recommendation is conditional on 20C outcome
- [ ] Follow-up PRD list drafted for (A) branch
- [ ] Cleanup checklist drafted for (B) branch, with `runtime.py` line-count-delta estimate
- [ ] Explicit note: no partial-commit
- [ ] Owner sign-off slot with final direction
- [ ] No code move, no deprecation notice pushed pre-sign-off

**PRD reference:** prd/063-multiplayer-commit-or-cut.md
