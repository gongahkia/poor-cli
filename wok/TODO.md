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

### P1.3 New crate: `wok-watcher`
- *Why:* `wok-ui/theme_watcher.rs` is bespoke; future config/lua reload + plugin reload need it. warp's `watcher` crate is the model.
- *Shape:* notify-rs wrapper w/ debounce + path-set subscription + coalescing channel.
- *Migration:* fold `theme_watcher.rs` into it; add config-reload + lua-reload subscribers.
- *Tests:* burst-write debounce; rename-then-write; symlink follow toggle.

### P1.4 New crate: `wok-sumtree`
- *Why:* scrollback in `wok-terminal/state.rs` and edit buffer in `wok-input/buffer.rs` are linear. O(n) line-index lookups will hurt at 100k+ scrollback. sum_tree gives O(log n).
- *Shape:* generic B-tree of `Item: Summary` w/ cursor + seek-by-dim. Keep it minimal — no rope-text specialization yet.
- *Adoption:* land crate first w/o consumers. Migrate scrollback in P2.3 only after benches show win.
- *Tests:* property — invariants under random insert/remove; cursor seek matches linear oracle.

---

## P2 — State and parsing

### P2.1 `wok-settings` crate w/ derive macro (port of warp `settings_value` + `_derive`)
- *Why:* `wok-app/config.rs` is 31k of hand-rolled serde + validation + defaults. Adding a setting touches 4 places. Derive collapses to one.
- *Shape:*
  - `wok-settings` — `Setting<T>` value type, `SettingsStore`, layered sources (env > user toml > defaults).
  - `wok-settings-derive` — proc-macro `#[derive(Settings)]` emits TOML schema, defaults, JSON-schema export for editor LSP, live-reload diff.
- *Migration plan:*
  1. New crate empty + derive.
  2. Mirror current TOML schema as `#[derive(Settings)] struct WokConfig`.
  3. Switch loader; keep old `config.rs` as adapter for one release.
  4. Delete adapter.
- *Tests:* round-trip TOML; defaults stable; layer precedence; rejects unknown keys w/ helpful error.

### P2.2 ANSI/CSI/DCS parser audit
- *Why:* warp ships 23k of parser + 33k of tests + `ESCAPE_SEQUENCES.md` spec. wok's `wok-terminal/terminal.rs` is 35k mixed concerns.
- *Action:* split parsing out of `terminal.rs` into `wok-terminal/parser.rs` + `parser_tests.rs`. Use warp's `ESCAPE_SEQUENCES.md` as a *spec checklist* (read-only reference). Add corpus tests covering: SGR 38;2/5, mouse 1006/1015, OSC 4/10/11/52, OSC 133 A–D, OSC 8 hyperlinks, DCS sixel, APC kitty graphics, mode 2026 sync update, mode 2027 grapheme.
- *Acceptance:* parser is pure (no terminal-state writes); state mutations live in `state.rs`; coverage report ≥ 90% on `parser.rs`.

### P2.3 Scrollback indexing on `wok-sumtree`
- *Why:* enable instant search jump + O(log n) viewport seek.
- *Action:* re-layer `wok-terminal/state.rs` scrollback as `SumTree<Line>` w/ `LineSummary { count, byte_len, has_block_marker }`.
- *Bench:* 100k-line scrollback; viewport scroll, search-next, block-nav-up.
- *Flag:* `scrollback_backend = "sumtree" | "vec"` until soak passes.

### P2.4 Block model split
- *Why:* `wok-blocks/block.rs` is 20k. warp factors block id, block index, block grid separately.
- *Action:* split into `block.rs` (record), `block_id.rs` (typed id), `block_index.rs` (id↔offset map), keep `triggers.rs`. Pure refactor, no behavior change.

---

## P3 — Input and completion

### P3.1 New crate: `wok-input-classifier`
- *Why:* enables paste detection, NL-vs-shell heuristics for future block annotation, safer auto-execute decisions.
- *Shape:* `classify(buf: &str) -> InputKind { Shell, Paste, Heredoc, Possibly NL, Empty }` + size/time hints.
- *Consumers:* `wok-input/editor.rs` (paste bracketing), `wok-blocks/triggers.rs` (block boundary hints).
- *Tests:* known shells, multi-line heredoc, large paste, mixed CRLF.

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

### P4.2 Recorder upgrade
- *Why:* `wok-terminal/replay.rs` exists; warp's `recorder.rs` shows productized record-and-share. Useful for bug repro.
- *Action:* `wok record <file.wokcast>` writes ts+stream tuples; `wok replay <file>` schedules them into a virtual terminal. Self-contained, no upload path.
- *Tests:* record-replay equivalence on golden corpus.

---

## P5 — Release discipline

### P5.1 Feature-flag rings
- *Why:* wok's "honest gap" roadmap needs gated rollouts.
- *Shape:* `wok-features` crate. `enum FeatureFlag { UnifiedInput, SumTreeScrollback, ProviderCompletion, ... }` w/ const arrays `DOGFOOD`, `PREVIEW`, `RELEASE`. Runtime check `FeatureFlag::X.is_enabled()` reads channel + env override `WOK_FLAGS=+X,-Y`.
- *Doc:* one-line per flag in `docs/FEATURE_FLAGS.md` (auto-generated from a `build.rs` step).

### P5.2 Channel metadata
- *Why:* parallel to warp's `channel_versions`. wok currently has no notion of dev/preview/stable.
- *Shape:* `wok-channels` crate exposing `Channel::current()`. Build sets it via `WOK_CHANNEL` env at compile time. Default `Dev`.
- *Use:* `doctor` reports channel; flag rings consult it.

### P5.3 `wok doctor` extension
- *Action:* extend `wok-app/setup_ops.rs` doctor to report: shell-integration status per shell, parser conformance (run a tiny escape-corpus through the live parser), feature-flag state, channel, GPU adapter info, font fallback chain, sumtree-vs-vec scrollback choice.

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

### P7.2 Block share
- *Why:* warp has share-block-modal. Local-first equivalent = export.
- *Action:* `Mod+Shift+X` exports selected block to `.md` (cmd, exit, cwd, output, duration). No upload. Stretch: `--ansi` flag preserves color.

### P7.3 Vim crate split
- *Why:* `wok-ui/vi_mode.rs` mixes UI + vim semantics. warp factors `vim` as its own crate.
- *Action:* new `wok-vim` crate w/ pure state machine `(Mode, Operator, Motion, Count, Register) -> Vec<Edit>`. `wok-ui/vi_mode.rs` becomes a thin view binding.
- *Tests:* operator+motion matrix golden; counts; registers `"a..z`, `"+`, `"*`.

### P7.4 Bootstrap consolidation
- *Why:* warp's `terminal/bootstrap.rs` + `available_shells.rs` (39k) is more thorough than wok's `wok-terminal/shell.rs` (6.5k) + `shell_integration.rs` (15k).
- *Action:* widen shell detection (nu, xonsh, elvish, ash, dash, ksh, csh, tcsh) w/ capability matrix `{ osc133, prompt_var, history_file, profile_path, alias_file }`. Failing capability → degrade gracefully + report via `doctor`.

### P7.5 Onboarding flow
- *Action:* `wok init` already exists. Extend into a 4-step onboarding: detect shell → install integration → seed config + theme → run smoke test (echo/false/pwd → expect 3 blocks). Idempotent. Output is plain text, scriptable.

### P7.6 Modal / safe-triangle / quit-warning polish
- *Why:* warp ships small UX modules (`safe_triangle.rs`, `quit_warning/`, `modal.rs`) wok lacks.
- *Action:* port the *patterns*, not code. Safe-triangle is a generic pointer-intent algorithm; quit-warning is a confirm modal w/ "running children" detection. Both <500 LoC each, written fresh.

### P7.7 Inline image consolidation
- *Why:* `wok-renderer/inline_images.rs` already exists. warp covers sixel + kitty + iTerm. Audit coverage; add kitty graphics if missing.

### P7.8 Snapshot recorder for bug reports
- *Action:* `wok bug-report` bundles config, last N PTY bytes (redacted), feature-flag state, doctor output → `bug-<ts>.tar.gz` in cwd. No upload.

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
