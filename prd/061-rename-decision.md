# PRD 061: Rename the project — DECISION

- **Wave:** 4
- **Status:** decision
- **Owner (human):** @gongahkia
- **Estimated effort:** small if (b); large if (a) (1–2w migration)
- **Blocks:** —
- **Blocked by:** —

## 1. Problem

"poor-cli" is memorable in a HN post and a drag in an enterprise eval. The name signals "inferior" rather than "cost-aware." Adoption ceiling. LONGTERM-TODO L5; LEARNING.md §4.3.

## 2. Current state

- pip package `poor-cli`
- GitHub repo `gongahkia/poor-cli`
- Neovim plugin `nvim-poor-cli`
- 10K+ lines of code referencing the name
- `.poor-cli/` state directory convention

## 3. Decisions required

> **DECISION 1:** rename yes / no?
> - (a) **Rename** — short-term migration pain; long-term adoption ceiling lifted.
> - (b) **Keep** — zero migration cost; brand risk stays.
>
> **DECISION 2 (if yes):** new name shortlist:
> - `thriftcode` — cost-virtue named.
> - `byokit` — BYOK + toolkit.
> - `frugal` — short, unambiguous, cost-virtue.
> - `parsimony` — principle-virtue.
> - `hive` — multiplayer implication.
> - `pactcode` — BYOK agreement tone.
> - Owner-proposed: _____________
>
> **DECISION 3 (if yes):** backward-compat strategy:
> - Ship `<newname>` AND `poor-cli` as an alias package redirecting to the new one for one major version.
> - State `.poor-cli/` → `.<newname>/` with auto-migration on first run.

**Recommended:** (a) + `frugal` (short, memorable, positive-framed). With backward-compat for one release.

## 4. Design (if (a))

- Create new repo `gongahkia/<newname>` (or rename existing).
- Rename pip package. Upload alias `poor-cli` → `<newname>` with deprecation warning.
- Rename Neovim plugin directory. Alias `nvim-poor-cli/` import path redirects.
- State directory rename with migration (PRD 003 framework).
- `poor-cli-server` → `<newname>-server`.
- Documentation pass.

## 5. Files to modify

Exhaustive. Search-and-replace after owner approves the new name. Estimated ~500 file touches.

## 6. Implementation plan

1. Owner decides.
2. If (a): new repo, pip alias published, docs pass, state migration.
3. If (b): close this PRD as wont-fix; update LONGTERM-TODO L5.

## 7. Testing & acceptance criteria

- Backward-compat: `pip install poor-cli` prints deprecation, still works.
- `.poor-cli/` auto-migrated.
- All docs refer to new name.

**Done criterion**
- [ ] New name shipped (if (a)) with backward-compat path.
- [ ] Docs pass.

## 8. Rollback / risk

High if (a). Mitigated by backward-compat alias for one release.

## 9. Out-of-scope & boundary

- 🚫 Do not rename without owner approval of both rename and new name.

## 10. Related PRDs & references

- LONGTERM-TODO L5.
- LEARNING.md §4.3, §6.
