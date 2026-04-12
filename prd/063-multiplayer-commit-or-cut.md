# PRD 063: Multiplayer — commit or cut — DECISION

- **Wave:** 4
- **Status:** decision
- **Owner (human):** @gongahkia
- **Estimated effort:** depends
- **Blocks:** 037
- **Blocked by:** 062

## 1. Problem

Multiplayer (WebRTC P2P with role-based RBAC and signed invites) is genuinely unique. No competitor has it. But: no demo, no UI affordance, no share-this-session button, no marketing. 2,000+ lines of code, 500+ lines of state machine in `runtime.py`. Current state is worst-of-both. LEARNING.md §4.5, §6.

## 2. Current state

Working in the server; minimal UI in Neovim; no demo; no landing-page showcase.

## 3. Decisions required

> **DECISION:**
> - (A) **Commit.** Make multiplayer a first-class surface: chat header "Share" button, `:PoorCliCollabQuick` invite flow, 2-minute demo video (LONGTERM-TODO M1), landing-page section. Unblocks PRD 037 and marketing spend.
> - (B) **Cut.** Move multiplayer code to `_experimental/multiplayer/` with a deprecation notice. Reduce `runtime.py` cognitive cost. Archive PRD 037.
> - (C) **Freeze.** Keep as-is; no new investment; no deprecation either.

**Recommended:** depends on PRD 062. If audience = (C) Small teams → (A). Otherwise → (B).

## 4. Design (if (A))

- Invite link UI in chat header.
- `:PoorCliCollabQuick` modal wizard.
- Multiplayer Room panel (PRD 037).
- 2-minute demo recording.
- Landing-page section.

## 5. Files to modify

Many (depends on decision).

## 6. Implementation plan

Per decision.

## 7. Testing & acceptance criteria

If (A): demo recorded; invite flow user-tested.
If (B): `_experimental/multiplayer/` exists; runtime.py drops 500+ lines.

## 8. Rollback / risk

(A): marketing misses. (B): bandwidth to reverse shrinks over time.

## 9. Out-of-scope & boundary

- 🚫 Do not partial-commit. Pick a direction.

## 10. Related PRDs & references

- PRD 037, 062.
- LEARNING.md §4.5, §6.
