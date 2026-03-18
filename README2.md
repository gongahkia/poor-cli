# README2

This file records project updates that were intentionally not merged into `README.md`.

## Multiplayer

- The executable multiplayer implementation is now invite-only, owner-authoritative P2P over WebRTC DataChannels.
- The canonical multiplayer behavior and operational details remain documented in `docs/MULTIPLAYER.md`.
- The removed executable bootstrap paths are:
  - `poor-cli-server --bridge --url ... --room ... --token ...`
  - `poor-cli --remote-url ... --remote-room ... --remote-token ...`
  - Neovim `multiplayer.url`, `multiplayer.room`, and `multiplayer.token`

## Validation

- Multiplayer session coverage now includes token rotation and revocation, pending-member approval, lobby disable approval, and fallback driver promotion.
- Multiplayer runtime coverage now includes stale invite rejection, pending approval plus driver handoff across two peers, and reconnecting with the same invite after disconnect.
- GitHub Actions now runs the multiplayer Python test suite so the P2P path is exercised in CI.
