# PRD NNN: [short imperative title]

- **Wave:** 1 / 2 / 3 / 4
- **Status:** draft / ready / claimed / in-progress / review / done
- **Owner (human):** @gongahkia
- **Assignee (agent):** _unassigned_
- **Estimated effort:** small (<1d) / medium (1–3d) / large (1–2w) / x-large (2w+)
- **Blocks:** `prd-0NN`, `prd-0NN`
- **Blocked by:** `prd-0NN`
- **Files it mutates (for conflict detection):**
  - `path/to/file1.py`
  - `path/to/file2.lua`
- **New files it adds:**
  - `path/to/new.py`

---

## 1. Problem

One or two paragraphs. What's wrong today. Cite exact file paths and line ranges where the problem lives. Assume the reader has **not** audited the repo; give them enough so they don't have to.

## 2. Current state

Read-only summary of how the current code behaves. The agent should be able to verify this in <5 minutes of reading the cited files. Quote 5–15 lines max where helpful — don't paste whole files.

## 3. Goal & non-goals

**Goal:** one sentence. What success looks like, observable from outside.

**Non-goals:** bullet list of tempting adjacent problems that are *explicitly not* part of this PRD. Rejects scope creep.

## 4. Design

The minimum architecture needed. Types, function signatures, flow diagrams in ASCII, data shapes. Don't write code the agent can write itself; do write the hard decisions (naming, boundaries, invariants).

Include a **DECISION REQUIRED** block for anything the owner must confirm:

> **DECISION REQUIRED:** [question]. Options: (a) ..., (b) ..., (c) .... Owner should answer before implementation begins.

## 5. Files to create / modify / delete

Exhaustive list, grouped:

**Create**
- `path/newfile.py` — one line purpose

**Modify**
- `path/existing.py:LL-LL` — what changes there
- `path/other.py:LL-LL` — what changes there

**Delete**
- `path/dead.py` — reason

## 6. Implementation plan

Numbered steps. Small enough that each step could be a commit. Call out tricky steps with a 🟠 marker. Call out destructive steps with a 🔴 marker that require human sign-off mid-execution.

## 7. Testing & acceptance criteria

- **New tests:** list each (`tests/test_foo.py::test_bar`) with the behavior they prove.
- **Commands to pass:** `make lint && make test`.
- **Manual verification:** e.g., `poor-cli exec --prompt "..."` should produce X.
- **Done criterion:** bulleted checklist the reviewer will tick.

## 8. Rollback / risk

What breaks if this lands and has to be reverted. What users might notice. Migration path for persisted state, if any.

## 9. Out-of-scope & boundary

Explicit list of files, modules, and features the agent **must not** touch in this PRD. Protect parallel PRDs from collision.

## 10. Related PRDs & references

- Other PRDs that touch nearby concerns.
- External links (standards, upstream projects, research papers).
- The specific LEARNING.md section this PRD implements.
