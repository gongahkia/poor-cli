# Walk Remaining Work Plan (for Independent Coding Agents)

This file defines everything still remaining after the current implementation batches.
It is intentionally detailed so an independent coding agent can execute without prior context.

## Non-Negotiable Operating Rules

1. **Atomic commits are mandatory.**
   1. One logical change per commit.
   2. Commit message must be **5-10 words**.
   3. If a task spans concerns, split into multiple commits.
2. **Do not edit `README.md`.**
   1. Any intended `README.md` change must be written to `README2.md` instead.
   2. If behavior changes, update `README2.md` and relevant `docs/*`.
3. **No remote-control end-to-end flow tests.**
   1. Do not add external E2E automation for remote control.
   2. Add **local test coverage only** (unit/integration in this repo).
4. **Never revert unrelated user changes.**
5. **No destructive git commands** (`reset --hard`, etc.).

## Current Baseline (Already Done, Do Not Redo)

1. Remote-control RPC surface exists (`walk.get_panes`, `walk.send_text`, etc.).
2. `walk rpc ...` CLI exists.
3. Replay mode + timeline markers exist.
4. Daemon lifecycle commands exist (`--daemon`, `attach`, `list`, `kill`, `detach`).
5. Daemon local integration coverage exists (`walk-app/tests/daemon_lifecycle.rs`).
6. Several `main.rs` extractions are complete (`rpc_cli`, `action_parser`, `jsonrpc_params`, `input_codec`, `remote_runtime`).

## Remaining Epics (Top-Level)

1. Complete `main.rs` decomposition into maintainable modules.
2. Move daemon from single-pane model to true multi-pane runtime.
3. Achieve attached-session parity for pane lifecycle and state synchronization.
4. Harden IPC/protocol contracts and validation (local tests only).
5. Improve local reliability/performance instrumentation and regression coverage.
6. Final packaging + documentation polish (`README2.md`, docs).

---

## Phase A — Finish `main.rs` Decomposition

### Task A1 — Extract workspace effect handling

**Purpose**
- Remove large workspace mutation logic from `walk-app/src/main.rs`.
- Improve reviewability and reduce regression risk when daemon-attached logic expands.

**Current Code Hotspot**
- `WalkHandler::apply_workspace_effect` in `walk-app/src/main.rs`.

**Target**
- New module: `walk-app/src/workspace_runtime.rs`.
- `impl WalkHandler` methods moved from `main.rs`:
  - `apply_workspace_effect`
  - `apply_layout_preset_cycle`
  - helper functions tightly coupled to those flows.

**Implementation Steps**
1. Create `workspace_runtime.rs` with `impl WalkHandler`.
2. Move methods with no behavior changes first.
3. Keep attached-mode guard semantics unchanged.
4. Remove moved methods from `main.rs`.
5. Resolve imports to module-qualified paths where needed.

**Local Tests**
- `cargo test -p walk`
- `cargo clippy -p walk --all-targets -- -D warnings`

**Done When**
- `main.rs` no longer contains workspace-effect `match` body.
- Behavior unchanged for tab/split/focus/layout/session actions.

**Atomic Commit Example**
- `Extract workspace effect handlers from main module`

---

### Task A2 — Extract rendering orchestration helpers

**Purpose**
- Rendering path is still concentrated and difficult to reason about.

**Current Hotspots**
- Large render helper functions in `main.rs` (status bar, overlays, replay rendering, quad batching helpers).

**Target**
- New module: `walk-app/src/render_runtime.rs`.
- Move render-only helpers and small rendering structs used only during frame draw.

**Implementation Steps**
1. Move pure rendering helpers first (no runtime mutation).
2. Move replay render helper and timeline rendering helpers.
3. Keep signatures stable during extraction.
4. Refactor imports minimally.

**Local Tests**
- `cargo test -p walk`
- `cargo test --workspace`
- `cargo clippy -p walk --all-targets -- -D warnings`

**Done When**
- Rendering helper code is isolated in `render_runtime.rs`.
- `main.rs` keeps orchestration only, not low-level draw details.

**Atomic Commit Example**
- `Extract render helpers from main runtime file`

---

### Task A3 — Extract CLI/session command dispatch

**Purpose**
- Startup/CLI path is currently mixed with runtime setup in `main.rs`.

**Target**
- New module: `walk-app/src/cli_runtime.rs`.
- Move:
  - command dispatch for `list/kill/detach/attach/rpc`
  - shared helper for daemon shell selection.

**Implementation Steps**
1. Define a small return enum (`ContinueToWindow`, `ExitOk`) for command handling.
2. Extract logic without changing behavior.
3. Keep CLI struct definitions in `main.rs` if needed; move only executable path.

**Local Tests**
- Existing unit tests + compile checks.
- Add one unit test for daemon shell override selection logic if extracted into pure function.

**Done When**
- `main()` becomes a short orchestration routine.

**Atomic Commit Example**
- `Extract CLI command dispatch from main function`

---

## Phase B — Daemon Multi-Pane Runtime

### Task B1 — Introduce explicit daemon session state

**Purpose**
- Current daemon loop has one implicit terminal. Needs pane map for parity.

**Target Files**
- `walk-app/src/daemon.rs`
- potentially `walk-app/src/ipc.rs` (protocol extension)

**Implementation Steps**
1. Add internal `DaemonSession` struct:
   - `panes: HashMap<u64, DaemonPane>`
   - `focused_pane: u64`
   - `next_pane_id: u64`
2. Add `DaemonPane` with:
   - `terminal: Terminal`
   - pane metadata needed for snapshots.
3. Initialize session with pane `0` (compat).
4. Route existing snapshot/input/resize through `DaemonSession`.

**Local Tests**
- Add daemon unit tests in `daemon.rs` for pane map behavior.
- `cargo test -p walk`

**Done When**
- Daemon internals no longer assume a single terminal variable.

**Atomic Commit Example**
- `Introduce daemon session and pane state model`

---

### Task B2 — Extend IPC for pane lifecycle operations

**Purpose**
- Attached mode cannot reach parity without daemon-side pane create/close/list methods.

**Target Files**
- `walk-app/src/ipc.rs`
- `walk-app/src/daemon.rs`

**Protocol Additions**
- `ClientMessage::CreatePane { direction }`
- `ClientMessage::ClosePane { pane_id }`
- `ClientMessage::GetPanes`
- `ServerMessage::PaneCreated { pane_id }`
- `ServerMessage::Panes { items: ... }`

**Implementation Steps**
1. Add new message enums with serde compatibility.
2. Implement daemon handlers with validation and errors.
3. Keep backwards compatibility for existing messages.
4. Ensure unknown pane-id errors are preserved.

**Local Tests**
- Unit tests in `ipc.rs` for message round-trips.
- daemon integration assertions (create/list/close).

**Done When**
- Local daemon APIs can create/list/close panes via IPC.

**Atomic Commit Example**
- `Add daemon pane lifecycle IPC message support`

---

### Task B3 — Expose daemon pane lifecycle in module API

**Purpose**
- `walk_app::daemon` needs public methods for runtime integration.

**Target Files**
- `walk-app/src/daemon.rs`

**Public API Additions**
- `create_pane(session: &str, direction: &str) -> Result<u64, ...>`
- `close_pane(session: &str, pane_id: u64) -> Result<(), ...>`
- `list_panes(session: &str) -> Result<Value, ...>` (or typed struct)

**Implementation Steps**
1. Add thin wrappers around IPC calls.
2. Keep existing API stable.
3. Document errors clearly (`pane not found`, `cannot close last pane`, etc.).

**Local Tests**
- Extend `daemon_lifecycle.rs` to assert pane lifecycle.

**Done When**
- `main.rs` can call daemon pane APIs without touching IPC internals.

**Atomic Commit Example**
- `Expose daemon pane lifecycle helper functions`

---

## Phase C — Attached-Session Parity

### Task C1 — Maintain local↔daemon pane mapping in attached mode

**Purpose**
- Current attached path maps all local panes to daemon pane `0`. This must evolve.

**Target Files**
- `walk-app/src/main.rs`
- extracted runtime modules as needed (`remote_runtime.rs`, `workspace_runtime.rs`)

**Implementation Steps**
1. Add mapping state in `WalkHandler`:
   - `daemon_pane_by_local: HashMap<PaneId, u64>`
2. Initialize mapping from daemon pane list on attach.
3. Keep fallback to pane `0` only when daemon returns single-pane snapshot.
4. Update send/resize routing to use mapping.

**Local Tests**
- unit tests for mapping initialization and fallback.
- integration test for multi-pane routing when daemon supports it.

**Done When**
- attached input/resize/snapshot are pane-aware.

**Atomic Commit Example**
- `Track local to daemon pane mappings`

---

### Task C2 — Route workspace pane mutations to daemon when attached

**Purpose**
- Current guard blocks mutations. After daemon multi-pane support, attached mode should support real pane operations.

**Target Files**
- `walk-app/src/workspace_runtime.rs` (or `main.rs` until extraction complete)

**Implementation Steps**
1. For `SplitVertical/Horizontal` in attached mode:
   - call daemon `create_pane(...)`
   - create corresponding local pane runtime state
   - update mapping table.
2. For `CloseSplit` in attached mode:
   - call daemon `close_pane(...)`
   - remove local pane and mapping.
3. Replace blanket mutation block with selective handling.

**Local Tests**
- integration test: attach + split + close + snapshot consistency.

**Done When**
- attached mode pane actions no longer blocked.

**Atomic Commit Example**
- `Route attached pane mutations through daemon API`

---

### Task C3 — Improve attached snapshot synchronization semantics

**Purpose**
- Current sync is append-only text hydration; weak for truncation/resets/pane churn.

**Target Files**
- `walk-app/src/remote_runtime.rs`

**Implementation Steps**
1. Track per-daemon-pane sync cursors.
2. Detect row reset/truncation conditions and perform pane rehydrate.
3. Handle pane addition/removal from `panes` snapshot array.
4. Add status messages only for user-relevant sync problems.

**Local Tests**
- unit tests for cursor advance/reset logic.
- integration: force reset path (e.g., clear screen command) and validate no stale content.

**Done When**
- attached pane content remains consistent after reconnect, clear, and pane lifecycle changes.

**Atomic Commit Example**
- `Make attached snapshot sync pane-aware and resilient`

---

## Phase D — Protocol and Runtime Hardening (Local Tests Only)

### Task D1 — Standardize JSON-RPC error responses

**Purpose**
- Keep protocol predictable for scripts.

**Target Files**
- `walk-app/src/remote_runtime.rs`
- `walk-app/src/remote_control.rs`

**Implementation Steps**
1. Use stable error code mapping:
   - `-32601` method not found
   - `-32602` invalid params
   - `-32000` runtime/server errors
2. Ensure parse failures and oversized payload behavior are explicit.

**Local Tests**
- unit tests for error payload structure and codes.

**Done When**
- all remote errors follow one consistent structure.

**Atomic Commit Example**
- `Normalize JSON-RPC error code handling semantics`

---

### Task D2 — Add request-level parameter validation helpers

**Purpose**
- Avoid repetitive ad hoc param handling in each method.

**Target Files**
- `walk-app/src/jsonrpc_params.rs`
- `walk-app/src/remote_runtime.rs`

**Implementation Steps**
1. Add typed extractors for common patterns:
   - `pane_id`
   - `row_range`
   - `action_name + params`
2. Replace duplicated parsing branches.
3. Keep behavior identical where possible.

**Local Tests**
- unit tests for each typed extractor.

**Done When**
- remote method bodies focus on business logic, not parsing boilerplate.

**Atomic Commit Example**
- `Add typed JSON-RPC parameter validation helpers`

---

## Phase E — Cross-Platform Gap Closure

### Task E1 — Windows remote control implementation (non-placeholder)

**Purpose**
- Current non-Unix remote control path is placeholder-only.

**Target Files**
- `walk-app/src/remote_control.rs`

**Implementation Steps**
1. Implement named-pipe server under `cfg(windows)`:
   - endpoint like `\\.\pipe\walk-<pid>`
2. Mirror current Unix semantics:
   - max clients
   - line-delimited JSON requests
   - per-request response.
3. Keep Unix path unchanged.

**Local Tests**
- unit tests that compile on non-Windows via abstraction.
- do not add remote-control E2E tests.

**Done When**
- `bind_default()` works on Windows builds instead of returning unsupported.

**Atomic Commit Example**
- `Implement Windows named-pipe remote control backend`

---

## Phase F — Local Performance and Reliability

### Task F1 — Add explicit runtime metrics snapshots

**Purpose**
- Improve debugging and perf regressions without E2E tooling.

**Target Files**
- `walk-app/src/main.rs` or extracted runtime modules
- `walk-ui/src/status_bar.rs` (if surfacing metrics)

**Implementation Steps**
1. Track:
   - frame pacing
   - pane count
   - replay snapshot memory estimate
   - daemon sync lag estimate.
2. Expose in debug overlay when enabled.

**Local Tests**
- unit tests for metric formatting utilities.

**Done When**
- metrics are visible and stable under debug mode.

**Atomic Commit Example**
- `Add runtime metrics collection and debug surfacing`

---

### Task F2 — Add stress-oriented local integration tests

**Purpose**
- Catch race/regression in daemon and attached runtime behavior.

**Target Files**
- `walk-app/tests/daemon_lifecycle.rs`
- additional `walk-app/tests/*` as needed

**Test Cases**
1. repeated attach/detach loops
2. multiple concurrent snapshot requests
3. invalid pane operations while session active
4. create/close pane churn after multi-pane support lands.

**Constraint**
- Local integration tests only. No GitHub remote-control E2E flows.

**Atomic Commit Example**
- `Add local daemon stress integration scenarios`

---

## Phase G — Packaging and Documentation Finalization

### Task G1 — Packaging script validation pass

**Purpose**
- Ensure release scripts remain coherent after runtime changes.

**Target Files**
- `packaging/linux/build_appimage.sh`
- `packaging/linux/build_deb.sh`
- `packaging/macos/bundle.sh`

**Implementation Steps**
1. Verify binary path (`walk`) assumptions.
2. Ensure shell integration assets are included.
3. Add comments/checks for missing dependencies in scripts.

**Local Validation**
- run scripts in supported local environment where possible.
- if not possible, at minimum add dry-run checks and script lint improvements.

**Atomic Commit Example**
- `Harden packaging scripts and bundle assumptions`

---

### Task G2 — Documentation sync (README2 + docs only)

**Purpose**
- Keep docs aligned with final daemon multi-pane + attached parity behavior.

**Files Allowed**
- `README2.md`
- `docs/ARCHITECTURE.md`
- `docs/CONFIGURATION.md`
- `docs/CLAUDE.md`

**Important**
- Do **not** edit `README.md`.

**Implementation Steps**
1. Update behavior descriptions and supported commands.
2. Document attached-mode capabilities and limitations.
3. Document any protocol additions.

**Atomic Commit Example**
- `Update docs for daemon and attached parity`

---

## Global Local Validation Matrix (Run Before Finalizing Any Batch)

1. `cargo fmt`
2. `cargo clippy -p walk --all-targets -- -D warnings`
3. `cargo test -p walk`
4. `cargo test --workspace`
5. Targeted integration tests introduced in the batch (for example: `cargo test -p walk --test daemon_lifecycle`)

If a task touches daemon IPC or attached sync logic, also run:
1. `cargo test -p walk --test daemon_lifecycle -- --nocapture`

## Commit Discipline Checklist (Per Batch)

1. Is each commit one concern only?
2. Is each commit message 5-10 words?
3. Did you avoid editing `README.md`?
4. If docs changed, did you update `README2.md` and appropriate `docs/*`?
5. Did local tests pass before committing?

## Suggested Execution Order

1. Phase A (remaining `main.rs` decomposition)
2. Phase B (daemon multi-pane internals)
3. Phase C (attached parity and pane mapping)
4. Phase D (protocol hardening)
5. Phase E (cross-platform remote control backend)
6. Phase F (local reliability/perf tests)
7. Phase G (packaging/docs final pass)

This order minimizes regression risk by first isolating modules, then changing daemon behavior, then integrating attached mode and tests.
