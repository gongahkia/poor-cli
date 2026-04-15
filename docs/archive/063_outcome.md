# PRD 063 Outcome: Multiplayer

**Date:** 2026-04-14

## Decision

**Outcome:** (A) Commit.

Owner sign-off keeps multiplayer as a first-class feature. PRD 037 is unblocked.

## Evidence

Multiplayer footprint counted on 2026-04-14:

| Area | Files | LOC |
|---|---:|---:|
| Python runtime/protocol | 7 | 4,734 |
| Neovim UI/tests | 4 | 669 |
| Docs | 1 | 194 |
| Total counted | 12 | 5,597 |

Counted files:

- `poor-cli/multiplayer.py` - 2,110 LOC
- `poor-cli/multiplayer_session.py` - 603 LOC
- `poor-cli/multiplayer_invites.py` - 134 LOC
- `poor-cli/server/multiplayer_state.py` - 1,310 LOC
- `poor-cli/server/multiplayer_runtime.py` - 422 LOC
- `poor-cli/server/handlers/multiplayer.py` - 125 LOC
- `poor-cli/_server.py` - 30 LOC
- `nvim-poor-cli/lua/poor-cli/multiplayer_room.lua` - 255 LOC
- `nvim-poor-cli/lua/poor-cli/collab.lua` - 209 LOC
- `nvim-poor-cli/lua/poor-cli/collab_ext.lua` - 117 LOC
- `nvim-poor-cli/tests/multiplayer_room_spec.lua` - 88 LOC
- `docs/MULTIPLAYER.md` - 194 LOC

`poor-cli/server/runtime.py` is now 344 LOC with zero direct `multiplayer` references. [Inference] The cognitive cost called out by the original PRD has moved into `poor-cli/server/multiplayer_state.py` and `poor-cli/server/handlers/multiplayer.py`, not disappeared.

No access: `LEARNING.md` is referenced by the PRD, but is absent in this checkout.

## Options

| Option | Cost | Benefit | Decision |
|---|---:|---|---|
| (A) Commit | Weeks; UI affordances, quick invite, demo, docs, landing copy, user testing | Makes the unique WebRTC/RBAC/signed-invite surface legible | Chosen |
| (B) Cut | Days; relocate code, simplify runtime, archive PRD 037 | Lowers maintenance load | Rejected by owner |
| (C) Freeze | Zero to one day; docs gate only | Keeps code without new work | Rejected by owner |

## Implementation

- Chat panel now has a Share affordance: press `S` to run `:PoorCLICollabQuick`.
- `:PoorCLICollabQuick [viewer|prompter]` starts or shares a collaboration invite and opens the room panel.
- `:PoorCLICollab start` and `:PoorCLICollab share` reuse the same invite-copy path.
- README and Neovim README position multiplayer as first-class.
- PRD 037 gate is resolved as commit.

## Demo Plan

The demo video is gating before the multiplayer marketing claim is launch-ready:

1. Host opens `:PoorCLIChat`.
2. Host presses `S` or runs `:PoorCLICollabQuick`.
3. Invite is copied and room panel opens.
4. Joiner runs `:PoorCLICollab join <invite>`.
5. `:PoorCLIRoom` shows both members and roles.
6. Host passes driver to the joiner.
7. Joiner sends `:PoorCLICollab suggest <text>`.
8. Both sides show the room event stream.

## Follow-Ups

- Record the 2-minute multiplayer demo.
- User-test invite flow with a clean Neovim config.
- Add a real README screenshot/GIF for chat Share and room panel.
- Keep `docs/MULTIPLAYER.md` as the protocol source of truth.

## Boundary

No partial-commit: multiplayer remains in product scope. Future work should improve this path rather than hide it behind experimental wording.
