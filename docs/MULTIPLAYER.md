# Multiplayer

This document is the source of truth for multiplayer behavior in this repository.
`README.md` intentionally remains unchanged during this migration.

## Status

- Current transport target: owner-authoritative P2P over WebRTC DataChannels
- Signaling/bootstrap surface: `aiohttp` owner endpoint on `/rpc`
- Compatibility bootstrap kept: `--url --room --token`
- Preferred bootstrap now: signed invite codes and `--remote-invite` / `--invite`

## Architecture

Multiplayer remains owner-authoritative.

- One owner process hosts the shared `PoorCLIServer` state.
- Joiners do not execute the shared backend themselves.
- Shared JSON-RPC traffic now targets a reliable ordered WebRTC DataChannel.
- `POST /rpc` is used for signaling/bootstrap.
- Existing room/session logic is transport-agnostic and lives in `poor_cli/multiplayer_session.py`.

The owner still controls:

- queue serialization
- room permissions
- lobby approval
- agenda state
- hand-raise queue
- driver handoff
- shared chat/tool execution

Passing driver changes who may act inside the room. It does not migrate ownership of the shared backend process.

## Session Model

The extracted session layer owns:

- role rebalancing between `viewer` and `prompter`
- room mode/preset mapping
- agenda creation and resolution
- hand raise state and next-driver selection
- room activity log shaping
- room event payloads
- token rotation and revocation

This state is used by both host-admin RPCs and live room notifications.

## Invites

The old invite shape was base64url of:

```text
url|room|token
```

The new primary invite shape is a signed base64url JSON envelope:

```json
{
  "payload": {
    "v": 1,
    "kind": "poor-cli-p2p",
    "signalingUrl": "wss://host.example/rpc",
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

- invites are signed with an owner-local secret
- invites can expire independently of the raw compatibility token
- legacy base64 `url|room|token` codes are still accepted by the Rust TUI and backend bridge
- host/share payloads now expose both signed and legacy invite forms

## Backend Transport

Backend files:

- `poor_cli/multiplayer.py`
- `poor_cli/multiplayer_session.py`
- `poor_cli/multiplayer_invites.py`
- `poor_cli/_server.py`

Owner host behavior:

- `GET /rpc` still serves the existing WebSocket runtime
- `POST /rpc` is now the signaling/bootstrap endpoint
- signaling currently supports:
  - `describe`
  - `connect`

Join bridge behavior:

- `poor-cli-server --bridge --invite <code>` is the preferred path
- `poor-cli-server --bridge --url <url> --room <room> --token <token>` is still supported
- the bridge now:
  - decodes invite/bootstrap data
  - creates a WebRTC peer connection
  - negotiates over owner signaling
  - forwards JSON-RPC over one ordered DataChannel
  - still injects `room` and `inviteToken` into `initialize`

Important runtime note:

- this workspace did not have `aiortc` installed during verification
- syntax and unit coverage passed, but an end-to-end WebRTC handshake was not executed locally in this thread

## TUI Workflows

The Rust TUI now treats invites as first-class.

CLI bootstrap:

- `poor-cli-tui --remote-invite <invite>`
- legacy: `poor-cli-tui --remote-url <url> --remote-room <room> --remote-token <token>`

Interactive flows:

- `/pair` still hosts
- `/pair <invite>` joins
- `/join-server <invite>` joins
- `/join-server <url> <room> <token>` still works
- reconnect now uses stored invite bootstrap when available

Internals:

- join/reconnect parsing is centralized in `poor-cli-tui/src/multiplayer.rs`
- shared library helpers in `poor-cli-tui/src/multiplayer_lib.rs` understand signed invites too

## Neovim Workflows

The plugin config now supports:

```lua
multiplayer = {
  enabled = true,
  invite = "...", -- preferred
  url = "...",    -- compatibility
  room = "...",   -- compatibility
  token = "...",  -- compatibility
}
```

New command:

```vim
:PoorCliCollab start [pairing|mob|review]
:PoorCliCollab join <invite>
:PoorCliCollab join <url> <room> <token>
:PoorCliCollab share [viewer|prompter] [room]
:PoorCliCollab leave
:PoorCliCollab pass [connection-id|display-name]
:PoorCliCollab suggest <text>
:PoorCliCollab members [room]
:PoorCliCollab status
```

Plugin behavior:

- invite bootstrap now starts `poor-cli-server --bridge --invite ...`
- join/leave uses restart-based bootstrap switching
- room notifications now surface agenda and hand-raise events in chat/status

## STUN and TURN

Config lives under `multiplayer` in `poor-cli` config:

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

- public Google STUN is enabled by default
- TURN entries are appended only when configured URLs and env-backed credentials are both present

## Compatibility

Kept stable:

- host/admin RPC names such as `poor-cli/startHostServer`, `poor-cli/getHostServerStatus`, `poor-cli/rotateHostToken`, `poor-cli/revokeHostToken`, `poor-cli/pairStart`
- room notifications:
  - `poor-cli/roomEvent`
  - `poor-cli/memberRoleUpdated`
  - `poor-cli/suggestion`
  - `poor-cli/streamingChunk`
- TUI slash commands:
  - `/pair`
  - `/collab`
  - `/join-server`
  - `/pass`
  - `/suggest`
  - `/leave`

Changed semantics:

- `url/room/token` is now signaling/bootstrap input, not the preferred direct room transport
- signed invite codes are the primary share format

## Verification

Executed in this thread:

- `python3 -m compileall poor_cli`
- `python3 -m unittest tests.test_multiplayer_invites tests.test_multiplayer_session`
- `cargo test --manifest-path poor-cli-tui/Cargo.toml backend_server_args_`
- `cargo test --manifest-path poor-cli-tui/Cargo.toml join_server_parser_`
- `cargo test --manifest-path poor-cli-tui/Cargo.toml remote_reconnect_classifier_`
- `luac -p nvim-poor-cli/lua/poor-cli/config.lua`
- `luac -p nvim-poor-cli/lua/poor-cli/rpc.lua`
- `luac -p nvim-poor-cli/lua/poor-cli/commands.lua`
- `luac -p nvim-poor-cli/lua/poor-cli/chat.lua`

Not executed here:

- end-to-end owner/joiner WebRTC handshake
- full Neovim interactive smoke test

Blocked reason:

- `aiortc` was not installed in the active workspace runtime

## Troubleshooting

- If `--bridge` fails with `missing_aiortc` or `ModuleNotFoundError: aiortc`, install Python dependencies from `requirements.txt`.
- If invite join fails at preflight, verify the signaling host/port is reachable, not just the room token.
- If TURN is configured but not used, check both `turn_urls` and the env vars referenced by `turn_username_env` and `turn_credential_env`.
- If Neovim join/leave appears to do nothing, inspect `:PoorCliStatus` and the server log path reported there; the plugin uses a restart-based bootstrap switch.
