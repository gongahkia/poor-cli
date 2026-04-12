# Getting started with the PRD pack

If you are the human owner: read §1–§4. If you are a coding agent: the human who assigned you a PRD has already done §1–§4; you go straight to your PRD file.

---

## 1. Which PRDs can start right now?

A PRD is **ready to claim** when:

1. Its `Status:` is `ready` (not `decision`, not `claimed`, not `in-progress`, not `done`).
2. Every PRD listed in its `Blocked by:` field is `done`.
3. Any upstream `decision` PRD that gates it has an `## Outcome` section you've filled in.

At initial ship (all 65 PRDs in `draft`/`ready`), the following **22 are ready to claim today** — no blockers, no upstream decisions:

### P0 correctness fixes (pick these first — unblock many downstream)
- **001** Unify token counting
- **002** Async-only permission callback
- **003** Schema-version persisted state
- **004** Semantic-cache content hash
- **005** File watcher consolidation

### Hygiene
- **006** Remove `_archived/` frontends
- **009** README rewrite + screenshot purge

### Security
- **010** RPC rate limiting
- **011** Audit log rotation
- **012** Keyring credential storage
- **013** Browser-tool JS sandbox

### Flagship UX (biggest single user-visible win)
- **014** Diff Review panel

### Cross-cutting infrastructure
- **065** Lua testing infrastructure — **spawn this before any Lua-test-shipping PRD**

### Wave 2 differentiators (not blocked on refactors)
- **023** AGENTS.md support
- **024** MCP 2026 compliance
- **026** RTK-lite shell filter

### Wave 3 panels (no backend dependencies)
- **034** Trust Center interactive
- **036** Policy Inspector
- **040** Onboarding rerun + tour

### Wave 3 integrations (new adapter files, low conflict)
- **050** `trouble.nvim`
- **052** `snacks.nvim`
- **054** `overseer.nvim`
- **055** Picker adapter layer
- **056** `neogit`
- **057** `nvim-dap`

### Research & bench
- **060** Publish SWE-bench Lite score

### Strategic decision PRDs — the human must answer these (see §2)
- **007** Stub modules decision
- **059** Latent communication decision
- **061** Rename decision
- **062** Target audience + north-star metric
- **063** Multiplayer commit-or-cut
- **064** Extension model consolidation

---

## 2. Decision PRDs — what to do before spawning dependents

Each `decision` PRD has a `## Decisions required` block with `DECISION REQUIRED:` questions. The human owner answers them like this:

Open the PRD file, scroll to the bottom, and append:

```markdown
## Outcome

_Decided 2026-04-12 by @gongahkia._

- Decision 1: (a) rename.
- Decision 2: `frugal`.
- Decision 3: publish backward-compat alias for one major version.

Rationale: [one or two sentences].
```

Then change the PRD's front-matter `Status:` to `ready` (it becomes implementable) or keep `decision` and assign to an agent with your answer pasted in — either works.

Recommended answering order (spend ~15 minutes on these before any spawning):

1. **062** — audience + north-star. Sets the frame for everything else.
2. **063** — multiplayer commit-or-cut. (Often answered by 062.)
3. **007** — stub modules. Fast, mechanical.
4. **059** — latent communication. (Often answered by 062.)
5. **064** — extension model consolidation.
6. **061** — rename. Can defer; least time-critical.

---

## 3. How to prompt a coding agent — copy-paste template

Paste this verbatim, replacing `<NNN>` and `<slug>`:

```text
You are assigned PRD 004 in the poor-cli repository.

Working directory: /home/gongahkia/Desktop/coding/projects/poor-cli
Your assignment: poor-cli/prd/<NNN>-<slug>.md

Rules:
1. Read your PRD top to bottom before writing any code. The PRD is self-contained —
   it has problem statement, file paths with line ranges, design, files to create/
   modify/delete, step-by-step plan, and acceptance criteria.
2. Check the `Blocked by` field. If any listed blocker is not yet merged to main,
   STOP and tell me before proceeding.
3. Check `Out-of-scope & boundary`. Do NOT modify files outside your PRD's scope,
   even if they look related — another agent may be working on them.
4. If the PRD contains a `DECISION REQUIRED` block without an `## Outcome` below
   it, STOP and ask me for the decision before writing code.
5. Follow TDD per the PRD's Testing section — write the failing test first when
   the change is behavioral.
6. Run `make lint && make test` before declaring done. If the PRD touches Lua,
   also run `make test-lua` (requires PRD 065 merged).
7. Work on a branch named `prd-<NNN>-<short-slug>`. One commit per implementation-
   plan step. Use conventional commit messages prefixed with `prd-<NNN>:`.
8. Open a PR titled `prd-<NNN>: <title>` when every Done-criterion checkbox in
   the PRD can be ticked. Do not merge — I will review.
9. Global conventions are in poor-cli/prd/README.md. The audit that generated
   these PRDs is poor-cli/LEARNING.md — only read it if you need extra context
   beyond what your PRD gives you.

Begin.
```

---

## 4. Recommended first spawn — 5 parallel agents

These five are maximally high-ROI and do not conflict with each other:

| # | Why first | Effort |
|---|---|---|
| **001** Token counter | Unblocks 017, 018, 027. The single highest-leverage bug fix. | medium |
| **014** Diff Review panel | Biggest user-visible win; LEARNING.md §3.1. | x-large |
| **065** Lua test infra | Prerequisite for every Lua-test-shipping PRD. | small |
| **055** Picker adapter | Prerequisite for 030, 032, 033, 046. | medium |
| **024** MCP 2026 compliance | Prerequisite for 035; independent of refactors. | large |

Then in a second parallel batch, spawn independent small PRDs: **002, 003, 004, 005, 006, 009, 010, 011, 012, 013**.

---

## 5. Coordinating the Wave 2 monolith chain

Wave 2 structural refactors **must serialize** because they all touch monolith files (`core.py`, `server/runtime.py`). Order:

```
001 ──┐
002 ──┴──► 017 (core pre-slice) ──► 018 (ContextAssembly) ──► 022 (PageRank)
                                ├──► 020 (ProviderCapability) ──► 027, 030
                                └──► 021 (core line-count gate)

010 ────► 019 (runtime partition) ──► 025 (streaming tool output) ──► 015
```

Only one agent works on `core.py` at a time. Only one works on `server/runtime.py` at a time. Assignment tip: the same agent can chain 017 → 018 → 021 since it already has the mental model.

---

## 6. How to track which PRD is in which state

The quick-and-dirty approach: update the PRD's front-matter `Status:` field and the index table in `prd/README.md`.

The slightly-better approach:

```bash
# PRDs ready to claim
grep -lE '^- \*\*Status:\*\* ready' poor-cli/prd/*.md | sort

# PRDs in progress
grep -lE '^- \*\*Status:\*\* in-progress' poor-cli/prd/*.md

# PRDs waiting on decisions
grep -lE '^- \*\*Status:\*\* decision' poor-cli/prd/*.md
```

The proper approach: use GitHub Issues, one per PRD. The PRD file is the spec; the Issue is the assignment + status. Wire a GH label per wave. (Not spec'd as its own PRD; do it when you feel it.)

---

## 7. If you want `poor-cli` to do it itself

Eat your own dog food:

```bash
cd /home/gongahkia/Desktop/coding/projects/poor-cli
source .venv/bin/activate

# spawn an agent on PRD 001
poor-cli exec --prompt "$(cat prd/001-token-counter-unification.md)
---
Follow the above PRD. Rules in prd/GETTING-STARTED.md §3."
```

For parallel agents, `poor-cli agent start --prompt ...` runs in a git worktree (see `Makefile::agent-start`). Agents writing to different files won't collide because each gets its own worktree.

---

## 8. What to do when a PRD is done

1. All Done-criterion checkboxes ticked.
2. `make lint && make test` (and `make test-lua` if applicable) green locally.
3. Change `Status:` to `done` in the PRD front-matter.
4. Move the file to `prd/_done/` (optional — keeps the top-level list tight).
5. Update the index table in `prd/README.md` (status column).
6. Identify newly-unblocked PRDs (the `Blocked by:` fields that pointed at this PRD are now resolved) and promote them to `ready`.

---

*This guide is versioned alongside the PRDs. If the process changes, edit this file.*
