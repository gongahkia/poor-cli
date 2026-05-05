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

### ~~P2.1 wok-settings + WokConfig schema~~ ✅ done
**Framework (earlier):** `wok-settings` crate w/ `Settings` trait, `SettingsSchema`, `SettingsStore<T>` (Defaults < UserToml < Overrides), `replace()` returning a `ChangedField` diff. `wok-settings-derive` proc-macro emits the impl. Self-derive supported via `extern crate self as wok_settings;`.

**Migration:** `WokConfig` now has a manual `wok_settings::Settings` impl in `wok-app/src/config.rs` that mirrors all 36 top-level TOML keys w/ stringified types. Manual rather than derived because the struct contains custom enums (ShellType, ChromeSide, BackgroundFit, …) that aren't all `Serialize` — derive would require a wider-scope refactor. Live-reload diffing can now name changed fields. 2 schema tests (known fields present, names unique). Adapter loader shim deferred — current `WokConfig::load` already implements the layered defaults+TOML behaviour the framework would otherwise wrap.

### ~~P2.2 Parser split~~ ✅ done (extraction)
Pure parser helpers extracted from `wok-terminal/src/terminal.rs` into a new `parser.rs` module: `find_osc_terminator`, `find_apc_terminator`, `find_dcs_terminator`, `find_csi_terminator`, `parse_kitty_keyboard_control`, `decode_kitty_image_data`, `parse_kitty_file_path`, `parse_osc8_params`, `sixel_display_size`, plus the `KittyKeyboardControl` enum. All `pub(crate)` so the dispatch loop in `terminal.rs` is unchanged. Tests moved + expanded: 14 parser tests (vs 6 before) covering OSC BEL/ST + EOF, APC ST-only, DCS dual-terminator, CSI final byte ranges, OSC 8 blank-token skipping, kitty RGB→RGBA padding, short-payload + unknown-format errors. Wider corpus (SGR 38;2/5, OSC 4/10/11/52, mode 2026/2027) deferred — they live in the dispatch loop and would require splitting more state-touching code.

### ~~P2.3 Scrollback mirror~~ ✅ done (mirror data structure)
`wok-blocks/src/scrollback_mirror.rs` lands. `LineSnapshot { absolute_row, block_id: Option<BlockId>, visible, is_boundary }` is a `SumTree::Item`; `LineSummary { total, visible, boundaries }` is its `Summary`. `ScrollbackMirror::{len, summary, push, get, nth_boundary, nth_visible, block_at_row}` — `nth_boundary` and `nth_visible` are O(log n) via `seek_by` over the boundaries/visible projections, validated against a 10k-line corpus. `block_at_row` is currently linear (real O(log n) needs a sorted secondary index — follow-up). 7 tests. The `alacritty_terminal::Grid` is still the source of truth for bytes; this mirror is metadata only and updates from `BlockManager` + viewport scroll wire in a follow-up PR (gated behind `FeatureFlag::SumTreeScrollback`).

### ~~P2.4 block model split~~ ✅ done
Split into: `block_id.rs` (`BlockId = u64` alias + `BlockIdGenerator` w/ `new`/`after`/`peek`/`next_id`), `block_index.rs` (`BlockIndex` w/ id→pos HashMap, O(1) lookup), `block_manager.rs` (state machine, uses generator + index). `block.rs` slimmed to record-only + re-exports `BlockManager` so external imports `wok_blocks::block::BlockManager` keep working. `restore_blocks` now rebuilds index. 25 tests pass (16 retained + 9 new across split modules).

---

## P3 — Input and completion

### ~~P3.1 wok-input-classifier~~ ✅ done (framework)
Crate landed w/ `classify(buf) -> Classification { kind: InputKind, hints: Hints }` and `kind(buf) -> InputKind` shortcut. Variants: `Empty | Heredoc | Paste | Shell | PossiblyNl`. Hints carry bytes/lines/has_crlf/has_nul. Heuristics in priority order: empty → heredoc (`<<` / `<<-` outside single quotes, w/ tag) → paste (≥4096 bytes or multi-line non-shell) → shell (known cmd, abs/relative path, top-level metas `|&;><$\``) → NL prose (≥3 words, no metas, no leading path). 13 tests. Consumers (`wok-input/editor.rs` paste bracketing, `wok-blocks/triggers.rs` boundary hints) wired in a follow-up PR.

### ~~P3.2 Completion engine~~ ✅ done (multi-provider runtime)
`wok-input/src/provider_runtime.rs` lands w/ `RankedRunner` (panic-isolated provider chain + dedup + fuzzy rerank via wok-fuzzy + max_results truncation), plus two new built-ins: `HistoryProvider` (prefix match against past commands) and `AliasProvider` (first-token only). Existing `completion.rs` providers (`PathCompletionProvider`, `CommandCompletionProvider`, `EnvVarCompletionProvider`) work unchanged with the new runner. 6 tests including panic isolation, dedup, truncation, empty-word passthrough. Fig-spec loader still deferred (filesystem-only loader fits in a follow-up). Migration flag swap (`FeatureFlag::ProviderCompletion`) lands when consumers switch over.

### ~~P3.3 Universal input surface~~ ✅ done (framework)
`wok-input/src/surface.rs` lands w/ `InputSurface { mode, slots: HashMap<SurfaceMode, ModeSlot> }`. `SurfaceMode::{Shell, Palette, Search, Find}` — each gets its own buffer + cursor (preserved across mode switches). API: `set_mode`, `text`, `cursor`, `set_text`, `insert_char`, `backspace`, `move_cursor`, `submit`, `cancel`. Returns `SurfaceAction::{Changed, Submit, Cancel, ModeChanged}`. Multi-byte safe — `backspace`/`move_cursor` step to char boundaries. 11 tests. Migration of existing `wok-app/input.rs`/`command_palette.rs`/`search.rs` consumers is the invasive part — lands behind `FeatureFlag::UnifiedInput` (already registered in `wok-features`) once views are factored.

---

## P4 — Testing and replay

### ~~P4.1 Integration harness~~ ✅ done (skeleton)
New crate `wok-integration`. `Builder::new().dims(c, r).scrollback(n).step(...).run() -> Harness`. Steps: `PtyOutput(bytes)`, `SendInput(bytes)`, `InjectEvent(SemanticEvent)`, `Resize { cols, rows }`, `Assert(Arc<dyn Fn(&Harness)->Result>)`. Wraps a real `TerminalState` + `BlockManager`, scripts feed semantic events for end-to-end block-detection coverage. `MockPty` records user input + queues scripted output. 6 unit tests including a 3-block scenario (`echo a / false / pwd` → 3 blocks, exit codes preserved). Real PTY adapters + virtual fs + fixed clock deferred — current scope covers parse → state → block-manager which is the hot path; shell-bootstrap goldens land when consumers do.

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

### ~~P6.1 wok-ui-core skeleton~~ ✅ done (framework)
New crate `wok-ui-core` distilling the entity-handle pattern (no `warpui_core` dep). `App` owns a type-erased `HashMap<EntityId, Rc<RefCell<dyn Any>>>` arena; `new_entity<T>(value) -> Handle<T>` returns a refcounted typed handle. `Handle::{read, write}` borrow w/ closure scope. `Entity<T>` is a copy-able id w/ compile-time T witness. `App::dispatch(entity, |&mut T, &mut Context|)` runs a handler and returns queued follow-up `Box<dyn Action>`s. `Context::new_entity` and `Context::emit` available inside the scope. `View::render() -> Element` w/ `Element::{Text, Container { tag, children }}`. Drop semantics: `App::drop_entity` invalidates new lookups but outstanding handles keep value alive (via Rc). 9 tests including dispatch on dropped entity = noop, handle clone shares storage, render produces tree, nested entity creation in handler. Migration of `WokHandler` substates is the follow-up; this crate gives them a target.

### ~~P6.2 Keymap framework~~ ✅ done (resolver)
New crate `wok-keymap`. Types: `Stroke { Key, Mods }`, `Key { Char, Enter, Esc, Tab, Backspace, Space }`, `Mods { ctrl, shift, alt, super_ }`, `Binding { sequence, action: &'static str, when: ContextPredicate }`, `ContextPredicate { Any, All, AnyOf, None_ }`, `Context = HashSet<&'static str>`. `Keymap::resolve(buffer, ctx) -> Resolution { Match { action, sequence_len } | Pending | None }`. Arbitration: a longer pending binding blocks a short exact match until disambiguated; same-length bindings are last-wins. 9 tests covering chord disambiguation, context masking, modifier-aware strokes, all four predicate kinds. TOML parser (`when:` opt-in) + migration from `wok-app/keybindings.rs` deferred to a follow-up.

---

## P7 — Product polish

### ~~P7.1 Block filtering~~ ✅ done (predicate combinators)
`wok-blocks/src/filter.rs` lands w/ `BlockFilter` (clone+send+sync `Arc<dyn Fn(&Block)->bool>`) and `and`/`or`/`not`/`any`/`none`. Built-ins: `failed_only`, `succeeded_only`, `running_only`, `matching_regex`, `cwd_under`, `since_id`, `command_contains`, `bookmarked_only`. `apply(blocks, &filter) -> Vec<usize>` returns matching indices in order. 13 tests including AND/OR/NOT, regex compile error, path-prefix, since-id strict-greater. Renderer integration + viewport sumtree caching deferred — they ride P2.3 once the scrollback mirror lands.

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

### ~~P7.7 Inline image audit~~ ✅ done (iTerm 1337 parser added)
Audit: `wok-renderer/inline_images.rs` is the protocol-agnostic store. Decoders: sixel ✓ (`wok-terminal/src/sixel.rs`), kitty graphics ✓ (`wok-terminal/src/terminal.rs::parse_kitty_apc`), iTerm OSC 1337 ✗. Gap closed by adding `wok-terminal/src/iterm_image.rs` w/ `parse(payload) -> ItermImagePayload { name, size, width/height: DisplayDim, preserve_aspect, inline, bytes }`. Handles `auto`/`<n>`/`<n>px`/`<n>%` dims, base64 name + bytes, forward-compat key skipping. 8 tests. Wiring into the OSC dispatcher in `terminal.rs` deferred (no consumer yet).

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

---

## P9 — Configurable keybindings (TOML override layer)

### ~~P9.1 TOML schema~~ ✅ done (commit `7d5fea9`)
`~/.config/wok/keybindings.toml` schema lands. `[[binding]]` entries with `keys`, `action`, optional `when`. Modifier syntax: `cmd|super|meta|win`, `ctrl|control`, `alt|opt|option`, `shift`. Final token is a single char or named key (`enter`, `pgup`, `f1..f12`, etc.). Action ids come from `parse_lua_action` (canonical strings shared with the Lua API). 8 loader unit tests.

### ~~P9.2 Loader + merge~~ ✅ done
Hot-reload via `wok-watcher::PathWatcher` polled per frame. `KeybindingConfig::apply_toml_overrides` upserts user entries on top of defaults; user wins on conflict. Unknown action names log warnings + drop only that entry. `wok doctor` now validates `keybindings.toml` and reports parse failures or dropped-entry warnings. Live reload now rebuilds each pane from defaults + Lua/plugin bindings + TOML, so bindings removed from the file disappear without restart.

### ~~P9.3 Editor UI~~ ✅ done
`Action::KeybindingEditor` opens an editable palette: each action shows the current/default binding, "Bind" captures the next key press into `~/.config/wok/keybindings.toml`, and "Reset" removes the user override for that action. The existing read-only `Action::KeybindingDiscovery` palette remains available for quick reference.

---

## P10 — Settings: structured editor (current = TOML buffer + discovery palette)

`Action::OpenSettings` opens `config.toml` in a text buffer editor (Mod+S to save). Commit `25e2ae8` adds `Action::SettingsDiscovery` — a structured *view* (palette listing every field + current value + type) that jumps to the TOML editor on select. The form-with-controls work below is still open.

### P10.1 Schema-driven form (still open)
- `wok_settings::Settings` schema is already implemented for `WokConfig`; the discovery palette uses it.
- Build a renderer that walks the schema and emits a control per field type:
  - `bool` → toggle
  - `f32`/`usize` → numeric input + slider
  - enum → dropdown (requires the enum to expose its variants — add `pub fn variants() -> &'static [&'static str]` per enum)
  - `Option<PathBuf>` → file picker + clear button
  - `Vec<TriggerConfig>` etc → "edit raw" escape hatch back to TOML buffer
- "Reset to default" per field.
- "Open as TOML" escape hatch keeps power-user workflow.

### P10.2 Live preview (still open)
- Settings changes apply to a temp `WokConfig` clone first; "Apply" persists. "Discard" reverts.

---

## P11 — Distribution + release ops

Zero of these exist. None of the product matters until users can download a signed binary.

### P11.1 Signed macOS .dmg
- `cargo bundle --target aarch64-apple-darwin --target x86_64-apple-darwin` → universal binary.
- Code-sign w/ Developer ID Application cert; notarize via `xcrun notarytool`; staple ticket.
- `create-dmg` for the disk image w/ background + drag-to-Applications shortcut.
- Test that downloading + double-clicking from a browser produces no Gatekeeper warning.

### P11.2 Linux packages
- `.deb` via `cargo-deb` — Ubuntu 22.04+ / Debian 12+.
- `.rpm` via `cargo-generate-rpm` — Fedora 40+ / RHEL 9.
- AppImage for distros without packaging.
- `flatpak` and `snap` are stretch goals.

### P11.3 Windows installer
- `wix`-based `.msi` w/ Authenticode signature (EV cert preferred for SmartScreen).
- Standalone `.exe` via `cargo-wix`.

### P11.4 Homebrew tap
- `homebrew-wok` repo with a `wok.rb` formula pointing at signed release tarballs.
- `brew install wok/tap/wok` Just Works.

### P11.5 Auto-update
- `tauri-plugin-updater` style: check a `latest.json` manifest at startup, download + verify signature, prompt restart.
- Opt-out via `[updates] check = false` in config.

### P11.6 Crash reporting (opt-in)
- `sentry-rust` integration; `[telemetry] crash_reports = false` is the default per charter.
- First-run dialog: "Send anonymous crash reports to help fix bugs? [Yes] [No]" — choice is sticky.

---

## P12 — Pitch + positioning

Wok rejects AI, cloud, telemetry-by-default by charter. That niche is real but needs to be marketed *as the niche*.

### Three taglines to A/B
1. **"The terminal that stays out of your way — and off the network."**
2. **"Blocks. Hot reload. Zero telemetry. No AI."**
3. **"A modern terminal for people who don't want their shell history in the cloud."**

### Target audiences (ranked)
1. **Privacy-conscious devs** — security researchers, infosec, journalists, people who switched from Warp after the cloud-history incident.
2. **Regulated industries** — finance, healthcare, defense — orgs where cloud sync is a compliance violation.
3. **Power users tired of bloat** — "I want blocks like Warp but I don't want an AI assistant or sign-in screen."
4. **Lua/scripting fans** — Wok's Lua plugin model is more open than Warp's workflow YAML.

### Anti-positioning (what wok is NOT)
- Not for people who want AI command suggestions.
- Not for teams that need shared shell sessions across machines.
- Not a Warp replacement — a Warp *alternative for a specific user*.

### Differentiators to lead with
1. **Hot reload everything** — config.toml, themes, Lua plugins. No restart.
2. **Lua plugin model** — full programmatic control over the terminal.
3. **Zero network** — disable Wi-Fi, run wok, every feature works.
4. **Local-first sessions** — all state in `~/.config/wok` and `~/.local/share/wok`. Backup is a `tar`.
5. **Channel + flag system** — ship features behind flags, soak in dogfood, promote to stable.

---

## P13 — Weaknesses → functional improvements

Each weakness from the strategic audit becomes a concrete ticket here.

| Weakness | Ticket | Owner of fix |
|---|---|---|
| No signed builds | P11.1 / P11.3 | release engineering |
| No installers | P11.1–P11.4 | release engineering |
| No auto-update | P11.5 | release engineering + UI |
| No crash reports | P11.6 (opt-in) | infra |
| macOS-first only | P8 | platform owners |
| Settings = TOML buffer only | P10 partial — discovery palette ✅ `25e2ae8`; form controls + live preview open | UI |
| Keybindings hardcoded | P9 partial — TOML overrides ✅ `7d5fea9`; editor UI w/ stroke capture open | UI + config |
| No theme picker | ~~done 2787829~~ ✅ | — |
| Lua API surface narrow | ~~done~~ ✅ — see P15 | — |
| No Lua plugin SDK | ~~done~~ ✅ — see P15 | — |
| Framework crates not wired | ~~done~~ ✅ — see P16 | — |
| No marketplace for Lua plugins | P14.1 (new) | infra |
| No "first 60 seconds" demo | P14.2 (new) | onboarding + docs |
| No website / landing page | P14.3 (new) | marketing |
| No demo video | P14.4 (new) | marketing |
| No competitor benchmarks | P14.5 (new) | benchmarking |

---

## P14 — Marketing + community

### P14.1 Lua plugin marketplace
- Plugins live in a single `wok-plugins` GitHub org; one repo per plugin.
- `wok plugin install <github_user/plugin_repo>` clones into `~/.config/wok/plugins/`.
- `wok plugin list` lists installed; `wok plugin update [name]` pulls.
- No central registry; just GitHub. Discovery via `awesome-wok` README.

### P14.2 First 60 seconds demo
- Extend `wok onboard` with an optional fifth step: "Show me what's cool."
- Plays a wokcast that demonstrates: hot config reload, theme switch via palette, block bookmarking, Lua plugin loading, recording a `.wokcast`.

### P14.3 Landing page (wok.sh or similar)
- One page. Hero screenshot. Three differentiators. One 30-second video. Download buttons (macOS / Linux / Windows). Pricing block. "View on GitHub" link.
- Static site (Astro / 11ty / plain HTML). Deploy to Cloudflare Pages or Netlify.

### P14.4 Demo video
- 30 seconds. Screen recording, no narration, captions only. Show: install → onboard → use blocks → switch theme via palette → record + replay a session.

### P14.5 Competitor benchmarks
- vs iTerm2, Wezterm, Alacritty, Ghostty, Warp.
- Metrics: cold start, scrollback render at 100k lines, paste 10MB, fork+exec latency, memory at idle / under load.
- Publish in `docs/BENCHMARKS.md` with reproducer scripts.

---

## P15 — Lua plugin SDK + API stability ✅ done

Tracked retroactively because it shipped as an epic outside the original P1–P14 scope.

### ~~P15.1 Lua API expansion~~ ✅
Eight namespaces added to scripting.rs across `94242d2` … `00781e0`:
- `wok.tabs.{new,close,next,prev,switch}`
- `wok.panes.{split_*,close,focus_*,*_floating}`
- `wok.history.{entries,search}`
- `wok.window.{set_title,toggle_fullscreen,set_opacity}`
- `wok.fs.{read,write,exists,list}` (sandboxed to `~/.config/wok/data` + `~/.local/share/wok`)
- `wok.clipboard.{copy,paste}`, `wok.pane_api.{send_input,info}`, `wok.blocks.list`

Total Lua surface: ~50 functions across 18 namespaces.

### ~~P15.2 Plugin SDK assets~~ ✅
- `docs/LUA_SCRIPTING.md` (commit `d6fd763`) — full prose API reference.
- `docs/wok.d.lua` (commits `9611802` + `14fb0e8`) — LuaCATS type defs w/ 86 `---@since 1.0.0` annotations.
- `docs/examples/{minimal,full,powerful}.lua` — copy-paste starters.
- `wok-app/tests/lua_hook_payloads.rs` (commits `587ebd7` + `f266c6b`) — 12 hook payload schema tests.
- `docs/LUA_API_STABILITY.md` (commit `76b2ec1`) — versioning policy + deprecation workflow.
- `wok.api_version = "1.0.0"` constant exposed to Lua.
- `CHANGELOG.md` (commit `681240d`) — 1.0.0 baseline.
- `.github/scripts/lua_api_lint.sh` + CI job (commit `413ce39`) — enforces `---@since` on every public surface.

### ~~P15.3 Open extensions~~ ✅ done
- Runtime warns once per session when deprecated Lua aliases are used (`wok.keymap` → `wok.bind_key`, `wok.action` → `wok.run_action`).
- CI runs `shellcheck` on `.github/scripts/lua_api_lint.sh`.
- CHANGELOG release links now point at `github.com/gongahkia/wok`.

---

## P16 — Tier-A wirings ✅ done

Once the framework crates landed, each had to be wired into `main.rs` to actually ship behavior. Tracked retroactively.

| Wiring | Commit | What user sees |
|---|---|---|
| iTerm 1337 inline images | `8abc669` | `imgcat`-style scripts now render in-terminal |
| Doctor shell capabilities | `8abc669` | `wok doctor` shows OSC 133 + integration support per shell |
| `wok replay <file>` CLI | `8abc669` | wokcast files play back to stdout |
| Live `config.toml` reload | `8abc669` | Edit config while wok runs → "config.toml reloaded" status |
| `share::strip_csi` in markdown export | `b1f58c1` | Block export `.md` is ANSI-clean |
| Paste/heredoc submit hint | `7fd29e6` | Status bar warns on big paste / heredoc |
| ProviderCompletion flag | `2b1d5f0` | `WOK_FLAGS=+ProviderCompletion` swaps to fuzzy-ranked completions |
| QuitWarning state machine | `42ab6c7` | Close-with-running-shells confirm shows live process count |
| BlockFilter failed count | `b2c0522` | Action shows "N failed blocks in pane" |
| ScrollbackMirror per-block push | `38b2b33` | Sumtree mirror populated on every block boundary |
| Vim state machine on InputEditor | `f2ebbf4` | `vim_enabled` field (key routing wiring still open) |
| Chord keymap parallel to flat | `395a213` | `KeybindingConfig::resolve_chord` available; bindings still empty by default |
| InputSurface accessors on palette/search | `e78e488` | `to_input_surface()` helpers ready for unified-input migration |
| `ui_core::App` mount on WokHandler | `d8c7545` | Empty entity arena ready for incremental main.rs decomposition |
| Theme picker / keybind discovery / settings discovery palettes | `2787829` + `25e2ae8` | Three new palette-driven UIs for theme switch, binding discovery, settings field discovery |
