# PRD 037: Multiplayer Room full-screen

- **Wave:** 3
- **Status:** ready
- **Estimated effort:** medium (1w)
- **Blocked by:** 063
- **Files it mutates:**
  - `nvim-poor-cli/lua/poor-cli/collab.lua`
  - `nvim-poor-cli/lua/poor-cli/collab_ext.lua`
  - `nvim-poor-cli/lua/poor-cli/commands.lua`
- **New files it adds:**
  - `nvim-poor-cli/lua/poor-cli/multiplayer_room.lua`
  - `nvim-poor-cli/tests/multiplayer_room_spec.lua`

## 1. Problem

Multiplayer is the unique differentiator but invisible in Neovim. LEARNING.md §4.5 raises the "commit or cut" question (PRD 063). If PRD 063 = commit, this PRD ships a proper room UI.

## 2. Current state

Collab panel lists state. No share-this-session button, no driver handoff UI, no chat room view.

## 3. Goal & non-goals

**Goal:** fullscreen (tab-scoped) buffer with:
- Room name + invite link (copy-to-clipboard button).
- Members list with roles (owner / prompter / viewer).
- Driver indicator + `[Pass driver]` action.
- Queue of hands-raised + `[Grant]` action.
- Event stream (join/leave/role-change/plan-events).
- Embedded chat input (room-scoped, separate from agent chat).

**Non-goals:**
- Do not implement voice / video.
- Do not change WebRTC transport.

## 4. Design

RPCs (most exist): `listMembers`, `passDriver`, `raiseHand`, `grantDriver`, `roomChat`, `roomEvents`, `getInviteLink`.

## 5. Files to create / modify / delete

See header.

## 6. Implementation plan

1. Unify RPCs.
2. Build layout.
3. Wire actions.
4. Tests.

## 7. Testing & acceptance criteria

- `test_members_rendered_with_roles`
- `test_pass_driver_updates_indicator`
- `test_hand_raised_appears_in_queue`

**Done criterion**
- [ ] Room surface usable end-to-end.
- [ ] Invite link copy works.

## 8. Rollback / risk

Low; gated behind PRD 063 decision.

## 9. Out-of-scope & boundary

- 🚫 Do not touch multiplayer transport.

## 10. Related PRDs & references

- PRD 063.
- LEARNING.md §4.5.
