# TODO - 30 March 2026

## Uncompleted Tasks From `docs/todo.md`

### Task 91 (B) +app - Remote Control Protocol
- [ ] `echo '{"jsonrpc":"2.0","method":"walk.get_panes","id":1}' | socat - UNIX-CONNECT:$WALK_SOCKET` returns a JSON list of panes.
- [ ] `walk.send_text(pane_id, "ls\n")` from an external script executes `ls` in the target pane.
- [ ] `walk.run_action("SplitVertical")` creates a new vertical split from an external script.
- [ ] The `$WALK_SOCKET` variable is available in spawned shells.
- [ ] Multiple external scripts can connect simultaneously without interference.

### Task 92 (B) +terminal +ui - Instant Replay
- [ ] `Mod+Alt+Shift+R` enters replay mode. Left/Right arrow scrubs through past terminal states.
- [ ] Block completion timestamps appear as markers on the timeline. `[` / `]` jumps between them.
- [ ] The status bar shows "REPLAY 2m30s ago" with the timestamp of the current snapshot.
- [ ] Exiting replay mode returns to the live terminal state.
- [ ] Memory usage does not grow unbounded - old snapshots are discarded.
- [ ] Replay works correctly with split panes (each pane has its own replay store).

## Remaining Implementations, Broken Flows, Or Stubs

1. Daemon attach flow is metadata-only, not terminal I/O attachment.
- `walk-app/src/main.rs` only calls `attach_session` and sets a status message (`Attached session ...`), then starts a normal local window.
- `walk-app/src/daemon.rs` does not host or forward a real PTY stream; `ClientMessage::Input` and `ClientMessage::Resize` currently return `ServerMessage::Ack` only.

2. `walk detach` CLI command is not implemented.
- `walk-app/src/main.rs` defines `CliCommand::{Attach, List, Kill}` only.

3. Daemon support is Unix-only.
- `walk-app/src/daemon.rs` non-Unix implementation returns `"daemon mode is currently supported on Unix only"`.

4. Kitty keyboard protocol still misses modifier-only/release event forwarding.
- `walk-app/src/input.rs` filters out non-pressed events (`if event.state != ElementState::Pressed { return None; }`).
- Modifier-only keys are still filtered by `translate_key_event` returning `None` for unrecognized named keys.

5. CI local parity status against `.github/workflows/ci.yml`.
- `cargo build --workspace`: pass
- `cargo test --workspace --quiet`: pass
- `cargo fmt --check`: pass
- `cargo clippy --all-targets -- -D warnings`: fail
- `cargo doc --no-deps --workspace`: pass (with one rustdoc warning)
- Current clippy failures are in `walk-terminal/src/sixel.rs`, `walk-renderer/src/inline_images.rs`, and `walk-terminal/src/terminal.rs`.
