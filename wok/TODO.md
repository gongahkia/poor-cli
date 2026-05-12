# TODO - Current Backlog

This file tracks work that is still actionable. Completed phase history has been
removed from this TODO; use `CHANGELOG.md`, docs, and git history for shippedq
details.

## Operating Principles

- Keep Wok MIT and clean-room. Do not paste from AGPL reference code.
- Preserve the product charter: local-first, no AI, no login, no cloud dependency,
  and no telemetry by default.
- Treat `wok-app/src/main.rs` as an integration shell, not the place where new
  behavior grows.
- Add product logic in focused modules or crates first, then wire it into
  `main.rs` through a small adapter patch.
- Prefer pure state machines for complex behavior. They should accept plain input,
  return typed output/effects, and have unit tests before UI/event-loop wiring.
- Use the existing action/effect pipeline for user-visible behavior:
  `Action` -> pane/workspace handler -> typed runtime effect.
- Expose automation through stable actions, Lua hooks, and JSON-RPC methods rather
  than exposing mutable internal renderer/layout state.
- Gate risky behavior swaps behind feature flags until they have soaked.
- Add integration or smoke coverage for every feature that crosses PTY, rendering,
  session, shell integration, or RPC boundaries.

## Known Limitations And Workarounds

### Runtime orchestration density

`wok-app/src/main.rs` still owns too much orchestration. The workaround is to make
it thinner incrementally:

- Move reusable logic into `workspace_runtime`, `render_runtime`, `remote_runtime`,
  `cli_runtime`, or a new focused module.
- Move domain logic into the owning crate (`wok-blocks`, `wok-input`, `wok-ui`,
  `wok-terminal`, `wok-git`) before adding app glue.
- Keep new `main.rs` changes adapter-shaped: route input, call a helper, apply
  typed effects, request redraw.
- If an integration patch becomes large, extract another runtime module before
  continuing.

### Plugin boundary

Plugins are currently action/hook scoped. They should be used for keybindings,
command aliases, lifecycle hooks, `run_action`, shell command injection,
notifications, status updates, and external bridge effects.

Do not design third-party extensions that require arbitrary mutation of Wok's
workspace, renderer, or layout internals. If a plugin needs a new capability, add a
bounded action, Lua API, or JSON-RPC method.

Custom panels, docks, and render surfaces should remain built-in until Wok has a
deliberate renderer/layout plugin API.

## P1 - Runtime Decomposition

Goal: keep shrinking `wok-app/src/main.rs` while preserving behavior.

- Extract action catalog and palette-entry construction out of `main.rs`.
- Extract Git/worktree command-palette and RPC helpers into a focused runtime
  module.
- Extract settings editor state/update/render preparation away from the top-level
  handler.
- Extract file/media preview orchestration into a runtime module that owns preview
  state transitions.
- Migrate suitable `WokHandler` substates into `wok-ui-core` entities once doing so
  removes real coupling.
- Add tests around each extracted module before deleting the old inline logic.

Acceptance:

- `main.rs` loses meaningful lines with no behavior loss.
- Extracted modules have direct unit tests where practical.
- `cargo test --workspace` passes after each slice.

## P2 - End-To-End Smoke Coverage

Goal: catch regressions that unit tests cannot see.

- Add smoke coverage for launch -> run command -> block created -> failed block
  navigation.
- Add shell marker goldens for Bash, Zsh, Fish, PowerShell, and WSL wrappers.
- Add session restore smoke for tabs, splits, transcript text, block timeline,
  collapsed state, and cwd.
- Add RPC smoke for `wok.get_panes`, `wok.send_text`, `wok.get_blocks`, and
  `wok.run_action`.
- Add daemon attach/detach smoke that verifies per-pane snapshot sync after pane
  creation and closure.
- Add at least one headless or screenshot-backed UI smoke for search/palette/dock
  layout if a reliable harness is available.

Acceptance:

- Smoke tests run in CI or are clearly marked as local/manual when they require a
  GUI.
- Failures produce enough context to identify shell, pane id, and command block
  state.

## P3 - Input And Keymap Migration

Goal: finish wiring the framework pieces that are already present.

- Complete `InputSurface` migration for palette/search/find/input surfaces.
- Decide whether `ProviderCompletion` should remain flag-gated or become default.
- Wire `wok-vim` key routing into owned input mode behind a config/feature flag.
- Use `wok-keymap` chord resolution for multi-stroke bindings once conflicts and
  timeout behavior are specified.
- Add paste/heredoc classifier behavior where it materially improves command
  submission safety.

Acceptance:

- Existing owned-primary input behavior stays compatible.
- Multibyte editing, completion, history recall, and cancel/submit flows have tests.

## P4 - Blocks, Scrollback, And Replay

Goal: harden the block model and recorder path beyond unit-level coverage.

- Add a sorted secondary index or equivalent for `ScrollbackMirror::block_at_row`
  if row lookup becomes hot.
- Decide where `SumTreeScrollback` should be enabled by default, if anywhere.
- Add before/after benchmarks for any scrollback or block lookup behavior swap.
- Add a true PTY tap for recording running panes, not only stdin `wokcast` input.
- Extend replay tests to cover resize, alternate screen, inline images, and block
  markers.
- Finish action-layer file output for block markdown/JSON export if not already
  wired for all intended surfaces.

Acceptance:

- Block boundaries remain stable after scroll, resize, search jumps, and session
  restore.
- Recorder/replay artifacts are deterministic enough for regression testing.

## P5 - Remote Control And Automation

Goal: make automation richer without exposing internals.

- Add bounded RPC/Lua capabilities only when they map to stable actions or stable
  read-only snapshots.
- Keep destructive RPC methods confirmation-gated.
- Add schema tests whenever `REMOTE_RPC_SCHEMA_V1.json` changes.
- Add Lua examples for common local workflows: failed-command notification,
  workspace save/load, Git status, scratch-to-pane, and block export.
- Keep the plugin bridge effect-only unless a deliberate extension API is designed.

Acceptance:

- External automation can compose Wok workflows through actions and snapshots.
- No plugin path can bypass the core action/workspace pipeline.

## P6 - Platform Hardening

Goal: improve confidence outside the best local demo path.

- Soak Bash, Zsh, Fish, PowerShell, and WSL shell bootstrap behavior.
- Add doctor checks for cheap GPU adapter diagnostics.
- Add doctor checks for scrollback backend/feature-flag state when exposed.
- Review macOS, Linux, and Windows packaging readiness separately.
- Keep startup/reset/onboard flows idempotent and rollback-safe.
- Ensure platform-specific process, notification, open/reveal, and shell behaviors
  degrade clearly when unavailable.

Acceptance:

- `wok doctor` explains setup problems without requiring source-level debugging.
- Platform-specific failures do not corrupt managed config or shell startup files.

## P7 - Product Positioning

Wok's niche is part of the product, not just implementation detail: blocks and a
modern workspace terminal without AI, cloud sync, login, or telemetry by default.

### Taglines To A/B

1. "The terminal that stays out of your way - and off the network."
2. "Blocks. Hot reload. Zero telemetry. No AI."
3. "A modern terminal for people who don't want their shell history in the cloud."

### Target Audiences

1. Privacy-conscious developers: security researchers, infosec, journalists, and
   people avoiding cloud terminal history.
2. Regulated industries: finance, healthcare, defense, and teams where cloud sync
   is a compliance issue.
3. Power users tired of bloat: people who want block workflows without an assistant
   or account system.
4. Lua/scripting users: people who want a programmable local terminal.

### Anti-Positioning

- Not for people who want AI command suggestions.
- Not for teams that need shared cloud shell sessions.
- Not a generic clone of another terminal; it is a local-first alternative for a
  specific user.

### Differentiators To Lead With

- Local-first by design; every core feature works offline.
- Command blocks are the workflow wedge.
- Lua scripting and JSON-RPC provide automation without cloud services.
- Config, themes, keybindings, and scripts are local files.
- Feature flags and channels allow risky work to soak before promotion.

## Non-Goals

- AI, agents, MCP, LLM glue, or command prediction.
- Cloud sync, accounts, billing, GraphQL/Firebase-style service backends, or
  hosted shell history.
- Telemetry by default.
- Crash-report upload or autoupdate.
- WASM target support unless a concrete local-first use case appears.
- Voice input, notebook features, code-review UI, or cloud share-block features.
- SQLite/Diesel persistence unless scrollback persistence proves it needs a real
  database.

## Tracking

- Open issues should link to the relevant section here and include acceptance
  criteria.
- Large behavior swaps should name their feature flag and soak plan.
- PRs should keep completed implementation notes out of this file; move shipped
  details to docs or changelog instead.
