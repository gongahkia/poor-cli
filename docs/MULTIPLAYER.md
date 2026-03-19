# Multiplayer

This document is the source of truth for multiplayer behavior in this repository.
`README.md` now reflects the current invite-only bootstrap at a high level; this
document remains canonical for protocol, operational, and compatibility detail.

## Status

- Multiplayer is owner-authoritative P2P over WebRTC DataChannels.
- The owner exposes an HTTP signaling endpoint at `POST /rpc`.
- Direct WebSocket room transport is removed.
- Join bootstrap is invite-only.

## Architecture

One owner process hosts the shared `PoorCLIServer` state for each room.

- The owner is responsible for shared chat state, tool execution, approvals, queueing, lobby decisions, agenda state, and role updates.
- Joiners connect to the owner by exchanging a WebRTC offer and answer through `POST /rpc`.
- After signaling completes, all room JSON-RPC traffic runs over one reliable ordered DataChannel.
- Passing driver changes which approved participant may act. It does not migrate owner authority or the shared backend process.

The transport-agnostic session layer lives in `poor_cli/multiplayer_session.py` and owns:

- role balancing
- lobby approval state
- agenda state
- hand-raise queue state
- room activity snapshots
- room event payload shaping
- internal invite token rotation and revocation

## Invite Format

Invites are signed base64url JSON envelopes. They are the only supported join bootstrap format.

```json
{
  "payload": {
    "v": 1,
    "kind": "poor-cli-p2p",
    "signalingUrl": "https://host.example/rpc",
    "sessionId": "dev",
    "role": "prompter",
    "token": "tok-...",
    "expiresAt": "2026-03-19T00:00:00+00:00",
    "ownerId": "owner-...",
    "ownerName": "host",
    "ownerFingerprint": "abcd1234...",
    "iceServers": [
      { "urls": ["stun:stun.l.google.com:19302"] }
    ]
  },
  "sig": "..."
}
```

Notes:

- `signalingUrl` is an HTTP endpoint, not a WebSocket endpoint.
- The embedded `token` is an internal room grant consumed by the owner after signaling succeeds.
- `rotateHostToken` and related host RPC names remain for compatibility, but they now issue or revoke invite-backed room grants rather than exposing a raw end-user join flow.

## Backend Interfaces

Files:

- `poor_cli/multiplayer.py`
- `poor_cli/multiplayer_session.py`
- `poor_cli/multiplayer_invites.py`
- `poor_cli/_server.py`

Current backend behavior:

- `POST /rpc` supports signaling `connect`.
- `GET /rpc` does not exist anymore.
- `poor-cli-server --host` starts the owner signaling service.
- `poor-cli-server --bridge --invite <code>` starts the stdio bridge joiner.
- `poor-cli-server --bridge --url ... --room ... --token ...` is removed.

Room notifications kept stable:

- `poor-cli/roomEvent`
- `poor-cli/memberRoleUpdated`
- `poor-cli/suggestion`
- `poor-cli/streamingChunk`

Host/admin RPC names kept stable:

- `poor-cli/startHostServer`
- `poor-cli/getHostServerStatus`
- `poor-cli/stopHostServer`
- `poor-cli/rotateHostToken`
- `poor-cli/revokeHostToken`
- `poor-cli/pairStart`

Their payloads are now invite-first and signaling-first.

## TUI Workflows

CLI bootstrap:

- `poor-cli-tui --remote-invite <invite>`

Interactive flows:

- `/pair` starts a hosted session
- `/pair <invite>` joins a session
- `/join-server` opens the invite prompt
- `/join-server <invite>` joins directly
- `/collab join`
- `/collab join <invite>`
- `/pass`
- `/suggest`
- `/leave`

The join prompt is invite-only. Manual `url/room/token` entry is removed.

Host status and share flows now expose:

- signaling endpoints
- viewer invite codes
- prompter invite codes
- invite-based join commands

They no longer expose raw viewer or prompter join tokens.

## Neovim Workflows

Plugin bootstrap:

```lua
multiplayer = {
  enabled = true,
  invite = "...",
}
```

Supported command surface:

```vim
:PoorCliCollab start [pairing|mob|review]
:PoorCliCollab join <invite>
:PoorCliCollab share [viewer|prompter] [room]
:PoorCliCollab leave
:PoorCliCollab pass [connection-id|display-name]
:PoorCliCollab suggest <text>
:PoorCliCollab members [room]
:PoorCliCollab status
```

The plugin restarts the local server with `poor-cli-server --bridge --invite ...` when joining a remote session.

## STUN and TURN

Multiplayer config lives under `multiplayer` in the Python config.

Relevant fields:

- `signaling_bind_host`
- `signaling_port`
- `signaling_path`
- `share_host`
- `invite_ttl_seconds`
- `owner_name`
- `reconnect_grace_seconds`
- `ice_servers`
- `turn_urls`
- `turn_username_env`
- `turn_credential_env`
- `turn_realm`

Default behavior:

- public STUN is enabled by default
- TURN entries are appended only when URLs and credentials are configured

## Failure Behavior

- If signaling fails, the joiner never opens the room DataChannel.
- If a DataChannel send fails, the owner now tears the member down through the shared session cleanup path instead of silently deleting transport state.
- If a peer disconnects, the owner removes the room member, clears active requester state, prunes the hand-raise queue, and rebalances driver roles when needed.
- If the active driver disconnects, fallback role promotion is handled by the session layer.

## Compatibility Matrix

Still stable:

- owner-authoritative room semantics
- one active driver at a time
- queue-serialized shared requests
- slash command names in the TUI
- notification method names for the TUI and Neovim plugin
- host/admin RPC method names

Removed:

- direct WebSocket room transport
- `GET /rpc`
- legacy `url|room|token` invite parsing
- `--url --room --token` bridge bootstrap
- `--remote-url --remote-room --remote-token` TUI bootstrap
- Neovim `multiplayer.url`, `multiplayer.room`, and `multiplayer.token`
- `:PoorCliCollab join <url> <room> <token>`
- manual URL and token join wizard flow

## Verification

Verified during this migration:

- `python3 -m compileall poor_cli`
- `cargo test --manifest-path poor-cli-tui/Cargo.toml backend_server_args_`
- `cargo test --manifest-path poor-cli-tui/Cargo.toml join_server_parser_`
- `cargo test --manifest-path poor-cli-tui/Cargo.toml remote_reconnect_classifier_`
- `luac -p nvim-poor-cli/lua/poor-cli/config.lua`
- `luac -p nvim-poor-cli/lua/poor-cli/rpc.lua`
- `luac -p nvim-poor-cli/lua/poor-cli/commands.lua`
- `luac -p nvim-poor-cli/lua/poor-cli/chat.lua`
- `python -m unittest tests.test_multiplayer_invites tests.test_multiplayer_session tests.test_multiplayer_runtime` inside a Python 3.12 venv with `ffmpeg@7`, `aiohttp`, and `aiortc>=1.13,<1.14`

## Troubleshooting

- If bridge startup fails with `missing_aiortc` or `ModuleNotFoundError: aiortc`, install Python dependencies from `requirements.txt`.
- If invite preflight fails, verify the HTTP signaling endpoint in the invite is reachable.
- If internet peers cannot connect reliably, configure TURN and verify the referenced TURN credential env vars are present.
- If Neovim join or leave appears stuck, inspect `:PoorCliStatus` and the reported server log path.
