# PRD 007: Decide and execute on stub modules (`docker_sandbox`, `speculative_decoding`, `rtk_integration`)

- **Wave:** 1
- **Status:** decision
- **Owner (human):** @gongahkia
- **Estimated effort:** small per decision (~1h), medium-to-large if "ship"
- **Blocks:** 008
- **Blocked by:** —
- **Files it mutates / may delete:**
  - `poor_cli/docker_sandbox.py`
  - `poor_cli/speculative_decoding.py`
  - `poor_cli/rtk_integration.py`
  - `poor_cli/kv_cache_store.py`
  - docs referencing any of these

## 1. Problem

Four research / sandbox modules are carried as stubs or dead integrations:

- `poor_cli/docker_sandbox.py` — ~3 lines, just `pass`. The docs and README imply Docker-based OS isolation is supported. It is not.
- `poor_cli/speculative_decoding.py` — unwired, cloud-irrelevant; only helpful with local vLLM/Ollama.
- `poor_cli/rtk_integration.py` — 2-line stub. Phase 23 / SOLUTIONS.md document a "Rust Token Killer" with 60–90% claimed savings. No Rust binary ships.
- `poor_cli/kv_cache_store.py` — local-only (vLLM/LMCache), taking space in every cold-start for cloud users.

[`LEARNING.md` §1.5 & §1.6](../LEARNING.md) flags all four. The current "ship it but hide it" state is worst-of-both: users get no value, contributors pay cognitive cost, README is misleading.

## 2. Current state

For each file, quick facts:

| File | LOC | Wired into agent loop? | User-visible surface? |
|---|---|---|---|
| `docker_sandbox.py` | ~3 | No | README mentions Docker sandbox |
| `speculative_decoding.py` | ~214 | No | — |
| `rtk_integration.py` | ~2 | No | SOLUTIONS.md extensively |
| `kv_cache_store.py` | — | Loaded on init for local providers | — |

## 3. Goal & non-goals

**Goal:** each of the four files is either (a) fully shipped end-to-end with user-visible value, or (b) removed with docs updated. No more "concept car" stubs sitting in the primary module tree.

**Non-goals:**
- This PRD is a **decision doc**. Implementation of "ship" decisions spawns follow-up PRDs (e.g., PRD 026 for RTK-lite covers option (a) for rtk_integration). Implementation of "archive" decisions is just deletes + doc edits and can happen here.

## 4. Decisions required

For each of the four, the owner must choose:

### 4.1 `docker_sandbox.py`

- **(a) Ship:** implement OS-level isolation via Podman (rootless, supported on Fedora/Ubuntu) and/or Docker. Spawns a follow-up PRD (~2-week effort).
- **(b) Archive:** delete the file and remove "Docker sandbox" references from README / docs / LONGTERM-TODO.

> **DECISION REQUIRED:** (a) ship, (b) archive, or (c) defer with a tombstone note. **Recommended:** (b).

### 4.2 `speculative_decoding.py`

- **(a) Ship:** only meaningful for Ollama / vLLM. Integrate as a capability flag (see PRD 020). Significant work, niche payoff.
- **(b) Archive:** move to `poor_cli/research/speculative_decoding.py` gated behind feature flag (see PRD 008 for the relocation).
- **(c) Delete outright.**

> **DECISION REQUIRED.** **Recommended:** (b) — already captured by PRD 008's relocation + flag.

### 4.3 `rtk_integration.py`

- **(a) Ship as Python-only first cut:** PRD 026 covers this; start with `git status --porcelain` filter, no Rust binary needed initially. Expand later.
- **(b) Delete and retract the Phase 23 promise in SOLUTIONS.md.**

> **DECISION REQUIRED.** **Recommended:** (a) via PRD 026 — the savings are real on one command even without a Rust binary.

### 4.4 `kv_cache_store.py`

- **(a) Ship:** guard at init — only load when a local provider (`ollama`) is active.
- **(b) Move to `poor_cli/research/`** and lazy-import.
- **(c) Delete.**

> **DECISION REQUIRED.** **Recommended:** (a) — minimal code (runtime gate) and real utility for local users.

## 5. Files to modify or delete

Depending on decisions:

**Always modify**
- `docs/phase_0*.md`, `SOLUTIONS.md`, `LONGTERM-TODO.md` — strike references to archived modules; update references to shipped ones.
- `README.md` — remove "Docker sandbox" claim if 4.1 = (b).

**Delete if archived**
- Whichever files were decided "delete."

**Move if relocated to research/** (this is PRD 008's job — just flag here which ones go).

## 6. Implementation plan

1. Owner answers each of 4.1–4.4.
2. Record decisions at the top of this PRD in an `## Outcome` section (add when executing).
3. For each "archive/delete" decision:
   - Remove the file.
   - Remove references in docs / README / SOLUTIONS.md.
4. For each "ship" decision that has a dedicated PRD (e.g., PRD 026 for RTK), transfer ownership there.
5. For each "research relocation" decision, transfer ownership to PRD 008.
6. Close this PRD.

## 7. Testing & acceptance criteria

- `make lint && make test` green.
- `grep -rn "docker_sandbox\|speculative_decoding\|rtk_integration\|kv_cache_store" poor_cli/ docs/ README.md` returns only lines consistent with the decisions.
- Docs that previously promised a feature no longer do if the decision was "archive."

## 8. Rollback / risk

Low per decision. Deletions are recoverable from git.

## 9. Out-of-scope & boundary

- 🚫 Do not implement new features in this PRD beyond the cleanup required by decisions.
- 🚫 Do not rewrite README broadly (PRD 009).

## 10. Related PRDs & references

- PRD 008 (research relocation) — depends on this PRD's decisions.
- PRD 026 (RTK-lite) — depends on 4.3 = (a).
- LEARNING.md §1.5 (research-to-ship gap), §1.6 (delete list).
