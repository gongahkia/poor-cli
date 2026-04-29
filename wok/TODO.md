# TODO — Adopt-from-Warp Plan

[Inference] Plan derived from a structural diff of `warp/` (vendored AGPL reference) vs current wok crates. All ports are clean-room reimplementations under MIT unless noted. Warp source is **reference only**; do not paste AGPL code.

## 0. Ground rules

- *License:* wok = MIT. warp = AGPL-3.0 (except `warpui_core`/`warpui` = MIT). Never paste from AGPL crates. `warpui*` may be vendored verbatim.
- *Scope guard:* charter is local-first, no AI, no cloud, no login. Reject any port that drags net I/O, auth, telemetry-by-default, or LLM glue.
- *Crate hygiene:* one new crate per concern. Keep `wok-app/main.rs` (currently 325k) shrinking, not growing.
- *Testing gate:* every port lands w/ unit tests + at least one integration scenario via the new harness (Phase 4).
- *Bench gate:* PTY/render/scrollback ports require before/after `criterion` numbers in `wok-app/benches/`.
- *Feature flags:* gate every behavior swap behind a flag (Phase 5) until soaked.

## 1. Phase ordering rationale

Foundations → state → input → UI fwk → product polish. Each phase is shippable alone and reverts cleanly via flag.

```
P1 foundations (command, watcher, fuzzy_match, sum_tree)
  → P2 state (settings_value derive, escape_seq parser, history index)
  → P3 input (input_classifier, completion engine, universal input)
  → P4 testing (integration harness, recorder/replay)
  → P5 release discipline (feature flags, channels, doctor++)
  → P6 UI fwk decomposition (entity-handle, keymap rewrite)
  → P7 product polish (block filtering, share, vim crate, onboarding)
```

---

## P1 — Foundations (low risk, high leverage)

### ~~P1.1 wok-process~~ ✅ done
Crate landed w/ `Cmd` builder, `run`/`run_with`/`spawn_detached`/`sh`/`open_url`/`notify`. Migrated `wok-ui/links.rs`, `wok-app/perf_metrics.rs`, `wok-app/main.rs` system notifications, `wok-app/plugin_host.rs::shell_command`. PTY spawning stays in `wok-terminal` (uses `portable-pty::CommandBuilder`, not `std::process::Command`). Async wrapper deferred until first consumer needs it.

### ~~P1.2 wok-fuzzy~~ ✅ done
Crate landed w/ `score(query, candidate) -> Option<Score>` + `match_many`. Substring tier (prefix > mid), subsequence tier w/ boundary (`_-/. :\` + camelCase) + contiguity + position bonuses. 11 tests. `wok-ui/command_palette.rs` migrated. `quick_select.rs` doesn't fuzzy-rank (label-pick), no migration needed. Future consumer: `wok-input/completion.rs` re-rank in P3.2.

### ~~P1.3 wok-watcher~~ ✅ done
Crate landed w/ `PathWatcher::{new,with_debounce,swap,path,poll}`. Drains notify events, coalesces by debounce window. `wok-ui/theme_watcher.rs` reduced to thin adapter. `poll()` signature changed `&self → &mut self`; one call site in main.rs updated. Config-reload + lua-reload subscribers deferred to first consumer.

### ~~P1.4 wok-sumtree~~ ✅ done
B-tree (fanout 8) w/ `Item`/`Summary` traits. API: `push`/`extend`/`get`/`len`/`summary`/`iter`/`seek_by`. Splits root upward on overflow; cached child counts make `get` truly O(log n). 7 unit tests + criterion benches.

Bench numbers (release, 100k items, 1024 ops):
- `get` random: vec ≈ 0.3 ns/op, sumtree ≈ 17 ns/op — Vec wins for raw indexed access (expected; sumtree has overhead).
- `seek_by` row-lookup: sumtree ≈ 24 ns/op, scales O(log n). Vec equivalent can't do this in O(log n); the bench's vec_linear column is unreliable (LLVM elides the constant inner loop).
- Push (sequential append): negligible difference.

Conclusion: migrate scrollback to sumtree only where soft-wrapped line→logical row needs the seek_by win. Raw indexed access stays on Vec.

---

## P2 — State and parsing

### P2.1 wok-settings + derive (framework ✅ / migration deferred)
**Done:** `wok-settings` crate w/ `Settings` trait, `SettingsSchema { type_name, fields }`, `SettingsStore<T>` (Defaults < UserToml < Overrides layers), `replace()` returning a per-field `ChangedField` diff for live reload. `wok-settings-derive` proc-macro emits the `Settings` impl by walking named fields. Self-derive supported via `extern crate self as wok_settings;`. 7 tests.

**Deferred (separate PR):**
- Mirror `wok-app/config.rs` (31k) as `#[derive(Settings)] struct WokConfig`.
- Adapter shim around the current loader.
- Delete the adapter once stable.

The framework is shaped to absorb the migration without further API changes; the holdup is the careful per-field walk to preserve every existing TOML key.

### P2.2 ANSI/CSI/DCS parser audit
- *Why:* warp ships 23k of parser + 33k of tests + `ESCAPE_SEQUENCES.md` spec. wok's `wok-terminal/terminal.rs` is 35k mixed concerns.
- *Action:* split parsing out of `terminal.rs` into `wok-terminal/parser.rs` + `parser_tests.rs`. Use warp's `ESCAPE_SEQUENCES.md` as a *spec checklist* (read-only reference). Add corpus tests covering: SGR 38;2/5, mouse 1006/1015, OSC 4/10/11/52, OSC 133 A–D, OSC 8 hyperlinks, DCS sixel, APC kitty graphics, mode 2026 sync update, mode 2027 grapheme.
- *Acceptance:* parser is pure (no terminal-state writes); state mutations live in `state.rs`; coverage report ≥ 90% on `parser.rs`.

### P2.3 Scrollback indexing on wok-sumtree (re-scoped, deferred)
**Why deferred:** investigation showed scrollback storage is owned by `alacritty_terminal::Grid` (`wok-terminal/src/state.rs`). We don't control the underlying buffer, so a "swap-the-backend" flag isn't viable without forking alacritty.

**Re-scoped target for next attempt:** maintain a *parallel* `SumTree<LineSnapshot>` mirror that the renderer consults for:
- O(log n) row → block-boundary lookup (currently a linear scan in `wok-blocks/block_nav.rs`).
- O(log n) "find the Nth visible line under a filter predicate" once P7.1 block filtering lands.

The mirror would be updated when `BlockManager` mutates and on viewport scroll. Behind `FeatureFlag::SumTreeScrollback` (already registered in `wok-features`).

Holdup: requires deciding what `LineSnapshot` carries and where the mirror lives. Worth its own design pass before code.

### ~~P2.4 block model split~~ ✅ done
Split into: `block_id.rs` (`BlockId = u64` alias + `BlockIdGenerator` w/ `new`/`after`/`peek`/`next_id`), `block_index.rs` (`BlockIndex` w/ id→pos HashMap, O(1) lookup), `block_manager.rs` (state machine, uses generator + index). `block.rs` slimmed to record-only + re-exports `BlockManager` so external imports `wok_blocks::block::BlockManager` keep working. `restore_blocks` now rebuilds index. 25 tests pass (16 retained + 9 new across split modules).

---

## P3 — Input and completion

### ~~P3.1 wok-input-classifier~~ ✅ done (framework)
Crate landed w/ `classify(buf) -> Classification { kind: InputKind, hints: Hints }` and `kind(buf) -> InputKind` shortcut. Variants: `Empty | Heredoc | Paste | Shell | PossiblyNl`. Hints carry bytes/lines/has_crlf/has_nul. Heuristics in priority order: empty → heredoc (`<<` / `<<-` outside single quotes, w/ tag) → paste (≥4096 bytes or multi-line non-shell) → shell (known cmd, abs/relative path, top-level metas `|&;><$\``) → NL prose (≥3 words, no metas, no leading path). 13 tests. Consumers (`wok-input/editor.rs` paste bracketing, `wok-blocks/triggers.rs` boundary hints) wired in a follow-up PR.

### P3.2 Completion engine rewrite
- *Why:* current `wok-input/completion.rs` (9k) is shell-history-only. warp uses Fig spec corpus + ranked merge across providers.
- *Shape:*
  - `Provider` trait: `fn candidates(ctx: &CompletionCtx) -> Vec<Candidate>`.
  - Built-ins: history, filesystem (cwd-aware), executables-in-PATH, alias.
  - Optional: Fig-spec loader behind feature `fig_specs` (specs in `~/.config/wok/specs/` only — no network fetch).
  - Re-rank w/ `wok-fuzzy`.
- *Migration:* keep old behavior under flag `completion_engine = "legacy"`; new = `"providers"`.
- *Tests:* deterministic ordering for fixed corpus; provider isolation (one panic doesn't kill others).

### P3.3 Universal input surface
- *Why:* warp's `universal_developer_input.rs` (46k) is one editor that routes to shell/search/palette. Matches wok's `command_entry_mode = owned_primary` direction. Avoids three near-duplicate buffers in `wok-app/input.rs`, `wok-ui/command_palette.rs`, `wok-ui/search.rs`.
- *Action:* extract a `wok-input/surface.rs` `InputSurface` that owns buffer + mode (`Shell | Palette | Search | Find`) + key routing. Existing palette/search become thin views over it.
- *Risk:* invasive. Land behind `unified_input = true` flag; default off for one release.

---

## P4 — Testing and replay

### P4.1 Integration harness crate `wok-integration`
- *Why:* current per-crate tests can't cover end-to-end PTY → block → render flows. warp's `crates/integration` Builder/TestStep DSL is the model.
- *Shape:*
  - `Builder` — constructs a headless wok app w/ mock PTY, virtual fs, fixed clock.
  - `TestStep` — enum: `SendInput`, `WaitForBlock`, `AssertCell`, `Resize`, `Snapshot`.
  - `MockPty` — scriptable byte stream + ack on writes.
- *Targets:* shell bootstrap golden, block detection across bash/zsh/fish/PowerShell/wsl, search-jump cross-pane, session save/restore round-trip.
- *Run:* `cargo nextest run -p wok-integration`.

### ~~P4.2 wokcast format~~ ✅ done (codec)
`wok-terminal/src/cast.rs` lands w/ `CastWriter` + `CastReader` for a newline-delimited record format: header `# wokcast v1 cols=… rows=… started=…` + records `<elapsed_us> <base64_chunk>`. Comment/blank lines skipped on read; unknown header keys ignored (forward-compat). `schedule(&mut reader, speed) -> Vec<(Duration, Vec<u8>)>` produces relative-delay playback plans; `speed=0.0` collapses to instant for deterministic tests. 8 unit tests including round-trip + malformed input. Existing `replay.rs` (in-memory cell snapshots) is untouched — different concern. PTY tap into the writer + `wok record/replay` CLI subcommands deferred to a wiring PR.

---

## P5 — Release discipline

### ~~P5.1 / P5.2 feature flags + channels~~ ✅ done
`wok-channels` (Dev/Dogfood/Preview/Stable, picked at build via `WOK_CHANNEL`) and `wok-features` (FeatureFlag enum w/ dogfood/preview/release ring arrays + `WOK_FLAGS=+X,-Y` overrides). 4 starter flags reserved for later phases (UnifiedInput, SumTreeScrollback, ProviderCompletion, BlockFiltering); arrays empty until landed. 7+5 tests.

### ~~P5.3 doctor channel + flags~~ ✅ done
Doctor now prints `channel: dev` and `feature_flags: on=[…] off=[…]`. Remaining doctor work (parser conformance, GPU adapter, font fallback chain, sumtree backend) deferred until those subsystems land.

---

## P6 — UI framework decomposition

### P6.1 Vendor `warpui_core` (MIT) as reference for entity-handle pattern
- *Why:* wok README admits "main runtime orchestration still lives in one large entrypoint". `wok-app/main.rs` is 325k. Need a retained-mode UI w/ entity handles to break it apart.
- *Decision:* do NOT depend on `warpui_core` directly (heavy, opinionated, brings text-layout/clipboard/keymap that conflict w/ wok's). Instead, distill the entity-handle pattern into a minimal `wok-ui-core` crate.
- *Shape (minimal subset):*
  - `App` global w/ typed `Entity<T>` arena.
  - `Handle<T>` (cheap clone, refcount).
  - `Context<'_, T>` for borrow + emit.
  - `Action` trait + dispatch.
  - `View` trait returning `Element` tree.
- *Out of scope (for now):* presenter/scene/wgpu pipeline (keep current `wok-renderer`).
- *Migration:* incrementally lift `WokHandler` substates into entities. Target: shrink `main.rs` below 50k by end of P6.

### P6.2 Keymap rewrite
- *Why:* `wok-app/keybindings.rs` is 24k flat. warp's `warpui_core/keymap.rs` (36k) is context-scoped chord trees w/ arbitration.
- *Shape:*
  - `KeyContext` stack (e.g., `[Workspace, Pane, Editor]`).
  - `Binding { sequence: Vec<Stroke>, action: ActionId, when: ContextPredicate }`.
  - `Keymap::resolve(strokes, ctx) -> Resolution { Pending | Match(ActionId) | None }`.
- *Migration:* parser reads existing `~/.config/wok/keymap.toml`; add `when:` field opt-in.
- *Tests:* chord disambiguation; context masking; conflict reporting.

---

## P7 — Product polish

### P7.1 Block filtering & viewport virtualization
- *Why:* warp's `block_filter.rs` (29k) + `block_list_viewport.rs` (91k) shows block UX ceiling. wok lacks filtering ("show only failed", "since last `git push`", "matching regex").
- *Shape:* `wok-blocks/filter.rs` w/ predicate combinators; `wok-renderer` consumes filtered iterator; viewport caches Y-positions in sumtree (synergy w/ P2.3).
- *Tests:* correctness vs naive filter; scroll stability when filter toggles.

### ~~P7.2 Block share~~ ✅ done (formatter)
`wok-blocks/src/share.rs` lands w/ `format_markdown(&Block, &[String], OutputMode)` + `OutputMode::{Plain, Ansi}` + `strip_csi(&str)`. Emits self-contained `.md`: id, cwd, git branch (+`*` if dirty), exit code, duration, fenced cmd (`sh`), fenced output (`text` or `ansi`). Output text supplied by caller (Block records grid rows, not bytes; the terminal grid is the source). 9 unit tests. Keybind wiring + actual file write deferred to action layer.

### ~~P7.3 wok-vim state machine~~ ✅ done (framework)
New crate `wok-vim` w/ pure state machine. Inputs: `Stroke { Char(c), Esc, Enter, Backspace }`. Outputs: `Vec<Edit>` (`ApplyMotion`, `ApplyOperator`, `ApplyLinewise`, `InsertChar`, `BackspaceChar`, `InsertNewline`, `OpenLineBelow/Above`, `DeleteCharUnderCursor`, `PasteAfter/Before`, `Undo`, `EnterMode`). Modes: Normal/Insert/Visual/VisualLine/OpPending. Verbs: `i I a A o O x p P u v V`. Operators: `d c y` w/ linewise `dd cc yy`. Motions: `h j k l 0 $ w b e f<c> F<c> t<c> T<c>`. Counts (multi-digit) and `"<a..z>` registers. 22 tests covering operator+motion matrix, counts, registers, mode transitions. Existing `wok-ui/vi_mode.rs` (terminal-output navigation) is a *different* feature and is left untouched — wok-vim targets the editor-buffer use case that hasn't shipped yet.

### ~~P7.4 Bootstrap capability matrix~~ ✅ done (data table)
`wok-terminal/src/shell_capabilities.rs` — static `ShellCapability { name, osc133, prompt_var, history_file, profile_path, alias_file, has_integration }` array covering bash, zsh, fish, ash, dash, ksh, csh, tcsh, nu, xonsh, elvish, powershell. APIs: `lookup`, `integrated_shell_names`, `osc133_capable_names`. 7 unit tests including invariant `has_integration → osc133`. Decoupled from `ShellType` enum on purpose — wider detection + doctor reporting can wire it in a follow-up without rippling to ipc/jsonrpc/cli code.

### ~~P7.5 Onboarding flow~~ ✅ done
`wok onboard [--shell auto|bash|zsh|fish] [--no-install] [--overwrite]` runs 4 steps with `[N/4]` plain-text output: (1) detect shell, (2) seed config + theme + integration scripts under `~/.config/wok` (idempotent via existing `init_at`), (3) wire managed-block markers into the user's startup file (skippable with `--no-install`), (4) smoke check that the installed integration script advertises OSC 133 `;A` and `;D` markers — fail/warn/ok report. Re-running is safe (uses managed-block markers + `--overwrite` opt-in). Smoke is content-based (no PTY harness needed). 3 unit tests + manual CLI smoke verified.

### ~~P7.6 safe-triangle + quit-warning~~ ✅ done (algorithms)
- `wok-ui/src/safe_triangle.rs` — pure 2-D geometry. `intent_preserved(apex, cursor, Rect)` returns `true` iff the cursor is still inside the triangle from the previous pointer position to the target's near edge. Auxiliary: `Rect`, `Side`, `approach_side`. 7 tests.
- `wok-ui/src/quit_warning.rs` — pure state machine `QuitWarning` w/ `on_quit_request`/`on_running_children`/`confirm`/`dismiss`/`should_show`/`should_quit`. Effects `{Quit, Show, Hide, NoChange}`. 8 tests.
- Generic `modal.rs` deferred — too vague to port without a UI fwk decision (lands w/ P6.1).
- UI integration (mounting in menu/quit flows) follows the existing wok-ui adapter pattern; deferred to a feature PR.

### P7.7 Inline image consolidation
- *Why:* `wok-renderer/inline_images.rs` already exists. warp covers sixel + kitty + iTerm. Audit coverage; add kitty graphics if missing.

### ~~P7.8 wok bug-report~~ ✅ done (directory bundle)
`wok bug-report [--output <dir>]` writes a directory `bug-<unix_ms>/` (default in cwd) containing: `doctor.json`, copies of `config.toml`/`init.lua` (if present), `channel.txt`, `flags.txt`, `system.txt`, and a `README.txt`. No upload, no network. tar.gz packing intentionally deferred (no tar/gz dep on wok-app yet — directory is just as shareable). Last-N PTY bytes also deferred until P4.2 recorder lands. 2 unit tests + manual smoke verified output.

---

## Explicit non-goals (do not port)

- AI / agents / MCP / LLM glue (`crates/ai`, `app/src/ai*`, `app/src/ai_assistant`, `agent_*`, `prompt/`, `predict/`).
- Cloud sync / Drive / auth / billing / GraphQL / Firebase / `warp_server_client` / `remote_server`.
- WASM target (`serve-wasm`, `*_wasm`).
- Telemetry-by-default (`warpui_core/telemetry`, `app_focus_telemetry`).
- Crash reporting upload, autoupdate.
- Voice input, computer-use, prevent-sleep, antivirus integration.
- Notebooks, code review UI, voltron, share-block cloud bits.
- Diesel/SQLite persistence — keep wok's TOML snapshots; revisit only if scrollback persistence becomes a feature.

## Workstream sizing (rough)

| Phase | LOC est | Risk | Order |
|---|---|---|---|
| P1.1 wok-process | 1–2k | low | 1 |
| P1.2 wok-fuzzy | <500 | low | 1 |
| P1.3 wok-watcher | <500 | low | 1 |
| P1.4 wok-sumtree | 1–2k | med | 2 |
| P2.1 wok-settings + derive | 2–3k | med | 2 |
| P2.2 parser split | refactor | med | 3 |
| P2.3 sumtree scrollback | 1k + bench | high | 4 |
| P2.4 block split | refactor | low | 2 |
| P3.1 input classifier | <500 | low | 3 |
| P3.2 completion rewrite | 2–3k | med | 4 |
| P3.3 universal input | 3–4k | high | 5 |
| P4.1 integration harness | 2–3k | med | 3 |
| P4.2 recorder upgrade | <1k | low | 4 |
| P5 release discipline | <1k | low | 2 |
| P6.1 wok-ui-core | 3–5k | high | 5 |
| P6.2 keymap rewrite | 2–3k | med | 5 |
| P7 polish | varies | low–med | 6 |

## Tracking

Per item: open issue w/ label `port:warp`, link this section, attach acceptance criteria. Land behind a flag in P5 once available; flip default in next release if soak ≥ 2 weeks w/o regressions.

## Open questions

- Relicense to AGPL to allow direct lifts? [Speculation] cleaner but loses the MIT pitch in README. Default = no.
- Adopt `warpui_core` wholesale (MIT-compatible) vs distill? Default = distill (P6.1) to avoid pulling its text/clipboard/keymap that conflict w/ wok's.
- Keep Lua scripting alongside a future entity-handle plugin model, or migrate? [Inference] keep both; Lua = user-side, entities = internal decomposition.
