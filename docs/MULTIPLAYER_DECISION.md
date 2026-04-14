# Multiplayer Decision

**Decision:** Commit.

Multiplayer remains a first-class poor-cli feature. The product keeps invite-only, owner-authoritative WebRTC sessions with signed viewer/prompter invites, a Neovim room panel, role/member state, and driver handoff.

## User Surface

- Press `S` in `:PoorCLIChat` to share a prompter invite.
- Run `:PoorCLICollabQuick [viewer|prompter]` to start or share an invite.
- Run `:PoorCLIRoom` to open the multiplayer room panel.
- Run `:PoorCLICollab join <invite>` to join a signed invite from Neovim.

## Gating Deliverable

A 2-minute demo is required before using multiplayer as launch-ready marketing proof. The demo must show host Share, invite copy, join, room panel, member roles, driver handoff, and a peer suggestion/event.

Protocol and operations details remain in [MULTIPLAYER.md](./MULTIPLAYER.md).
