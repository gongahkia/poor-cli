# Wok Frontend Rework Plan

Status: proposal · Owner: TBD · Target: incremental rollout across `wok-ui`, `wok-renderer`, `wok-app`.

Wok's "frontend" is the wgpu-rendered chrome (winit + `wok-renderer`), not HTML. Reference points map to layout/interaction language, not CSS. The wedge stays sharp: local-first, no AI, no cloud, no login. Block-oriented review remains the product.

---

## 1. Reference Distillation

| Source | Steal | Skip |
| --- | --- | --- |
| Warp | Block cards w/ header chip (cmd · exit · duration); bottom command editor as a first-class surface; `Mod-P` palette as nav spine; sticky scroll-snap on blocks | AI panel; cloud share; account gate |
| cmux | Pane-as-document model; mux ergonomics over tab metaphor; status line w/ session + branch glyphs | Tmux key-leader maze |
| Ghostty | Quiet typography; native-feel chrome; fast first paint; theme as identity | Aggressive chrome minimalism (Wok needs more density) |
| Wave | Right-side inspector dock; persistent block sidebar timeline | Web-stack baggage |
| Zellij | Discoverable bottom-bar mode hints; bindings surface when relevant | Heavy multi-row status |
| Fig / inshellisense | Inline ghost-text completion; parameter hints under cursor | — |
| Raycast | Palette as command surface w/ typed args; recent/saved sections | — |

---

## 2. Design Principles

1. **Density without noise.** Power users live in this all day. Use restraint — affordances appear on focus/hover, not always-on.
2. **One focus slot.** A single bottom dock owns the active modal surface (editor / palette / search / scratch / media). Swap, don't stack.
3. **Block is the atom.** Every navigation, motion, and inspection idiom hangs off the block primitive.
4. **Pane-first, tabs second.** Tabs are workspaces of panes; panes are the unit of work.
5. **Motion is a budget.** Reserve for state transitions, never for input.
6. **Identity through typography + theme.** Two-mono pairing and committed theme defaults make Wok recognizable in a screenshot.
7. **No AI affordances.** Keep the wedge visible.

---

## 3. Layout Architecture

Three durable regions:

```
┌──────────────────────────────────────────────────────────┐
│ Tabstrip (thin)                                          │
├──────────┬──────────────────────────────────────┬────────┤
│ Timeline │                                      │ Insp.  │
│ Rail     │           Pane Grid                  │ Dock   │
│ (opt)    │                                      │ (opt)  │
├──────────┴──────────────────────────────────────┴────────┤
│ Bottom Dock (modal slot) + Status Spine                  │
└──────────────────────────────────────────────────────────┘
```

- **Tabstrip:** thin (≈22px). Workspace name + saved-snapshot indicator + unread block count per tab. No close-button noise; close via palette/keymap.
- **Timeline rail:** opt-in left rail, ≈14px. One pip per block, hue = exit status. Click jumps; mirrors `Mod-Up/Down`.
- **Pane grid:** existing split layout. Pane chrome reduced to a 1-line header (glyph · cwd basename · branch).
- **Inspector dock:** opt-in right panel, slide-in. Tabs: Inspect · Rerun History · Diff · Media Preview. Replaces existing modal `Open Block Inspector`.
- **Bottom dock:** single modal slot. Default = command editor. `Mod-P`/`Mod-F`/`Mod-Alt-X` swap modes. `Esc` returns to editor. Status spine sits underneath as a single line.

---

## 4. Block Card Primitive

Each block renders as a `Card` with four parts:

```
│▌ echo hello                ~/wok  main   ✓ 0   12ms   ⋯
│▌ ──────────────────────────────────────────────────────
│▌ hello
│▌ ──────────────────────────────────────────────────────
│▌ [rerun history · diff strip]
```

- **Gutter rail (left):** 3px accent stripe. Hue = exit status (success / failure / running / signal). Selected block gets an animated outline pulse on the rail only.
- **Header row:** `cmd · cwd · branch · exit-pill · runtime · overflow-menu`. Branch + cwd from `wok-git` + terminal cwd events. Overflow only on hover/focus.
- **Body:** terminal cells (existing renderer path).
- **Foot (optional):** rerun history strip or `wok-git` numstat diff strip. Off by default; `Mod-Alt-I` toggles.
- **Collapsed:** single line, accent stripe + cmd + exit-pill. Hover reveals duration.
- **States:** idle / hover / selected / collapsed / running. Running = subtle stripe shimmer (CSS-equivalent: animated gradient on the rail only, ≤1Hz).

Affordances on hover/focus: copy, rerun, inspect, pin. Always-on icons banned.

---

## 5. Bottom Dock (Modal Slot)

One slot, one focus.

| Mode | Trigger | Notes |
| --- | --- | --- |
| Editor (default) | — | Owned-primary input promoted to default (currently opt-in). Ghost-text completions from `wok-input-classifier` + history. Faint inline arg hints under the cursor line. |
| Palette | `Mod-P` | Raycast-style typed args. Sections: Recent · Saved · All. Result rows show binding + source crate. |
| Search | `Mod-F` | Regex toggle, scope chips (pane / tab / workspace / saved), results list. Promoted from popover to dock surface. |
| Scratch | `Mod-Alt-X` | Existing scratch palette, hosted in the dock instead of overlaid. |
| Media preview | palette `Preview …` | Existing GIF/MP4/image preview, framed in the dock to avoid stealing pane area when small. |

Status spine (single line under dock): `mode · pane · branch · session · search-count · contextual-bindings`. Bindings rotate with focused surface (Zellij idiom).

---

## 6. Pane & Tab Model

- Tabs are containers of pane layouts (existing). Tabstrip stripped to identity + count.
- Pane header: glyph + cwd basename + branch. No tab-style chrome per pane.
- Focus indicator = 1px accent border + brighter gutter rail on the focused pane's selected block.
- `Mod-Shift-P` / `Mod-Shift-N` cycle panes (reuse keymap convention).

---

## 7. Typography & Theme

- **Body mono:** distinctive, characterful — one of `Berkeley Mono`, `Commit Mono`, `Monaspace Neon`. Configurable in `wok-settings`; ship a curated default.
- **Chrome mono:** a contrasting mono used only in chrome labels (header chips, status spine, palette rows) — `Monaspace Xenon Italic` or `IBM Plex Mono`.
- **Pairing rule:** body ≠ chrome. Two-mono identity is the visual signature.
- **Theme:** Graph Box Dark stays the default. Add a paired light theme (`Graph Box Day`) and one bold alt (`Graph Box Neon`). Themes drive accent hues used by the gutter rail, tabstrip, palette selection, and search highlight.
- **No tokens leaked into code:** all colors flow through theme files; renderer reads via `wok-ui` theme loader.

---

## 8. Motion Budget

Allowed:

- Block collapse/expand: height tween (≤120ms) + brief accent flash on rail.
- Palette open/close: 8–12ms fade + 2px lift.
- Search result jump: scroll-snap + 200ms highlight halo on the matched block.
- Rerun comparison reveal: 150ms slide-down on the foot strip.
- Running-block shimmer: ≤1Hz on the gutter rail only.

Forbidden:

- Animation on every keypress.
- Cursor-tracking glow.
- Shadow drifts on hover.
- Tab switch animations longer than 60ms.

Rule: if it animates while the user is typing, it's a bug.

---

## 9. Cross-Surface Behaviors

- **Timeline rail ↔ block selection:** rail click and `Mod-Up/Down` are equivalent. Selection in pane scrolls rail to keep selected pip in view.
- **Inspector dock ↔ selection:** when pinned, dock auto-follows selected block. Manual pin breaks auto-follow until cleared.
- **Search → block:** result jump selects the block, scrolls pane, halos the match. Repeated jumps cycle.
- **Palette → action:** every palette entry shows its keybinding (if any) and its origin (built-in vs. Lua alias).

---

## 10. What Stays Out

- AI panel, suggestions, completions sourced from a model.
- Cloud share / sync.
- Account / login affordances.
- Warp-style "did you mean…?" prompts.
- Notification center / toast spam. Use the status spine instead.

---

## 11. Sequencing (cheap → expensive)

1. **Theme + typography pass.** Theme files + font defaults only. No engine changes. Ship `Graph Box Day` and `Graph Box Neon`. Wire two-mono chrome.
2. **Status spine consolidation.** `wok-ui` only. Collapse current status surface to one line w/ rotating bindings.
3. **Block card refinement.** Gutter rail, header row layout, hover affordances, collapsed state polish. `wok-blocks` + `wok-renderer`.
4. **Bottom dock unification.** Promote owned-primary editor to default. Move palette / search / scratch / media into the modal slot. `wok-app` + `wok-input` + `wok-ui`.
5. **Timeline rail (left).** New renderer surface; backed by block index already in `wok-blocks`.
6. **Inspector dock (right) + search-as-dock.** Bigger; touches scroll model and split layout.
7. **Pane-first tab redesign.** Touches `WokHandler` orchestration; ship last to avoid churn.

Each step should land behind a config flag where feasible (`ui.layout = "v2"` etc.) so users can opt in during stabilization.

---

## 12. Open Questions

- Two-mono fonts: ship bundled or rely on user-installed? Licensing review needed for Berkeley Mono / Commit Mono.
- Timeline rail at 1000+ blocks: pip pooling vs. virtualization in the renderer.
- Inspector dock and small windows: minimum width before it auto-hides.
- Light theme parity: does the gutter-rail accent palette translate, or do we need a separate accent set?
- Owned-primary as default: regression risk on Bash/Zsh/Fish/PowerShell/WSL bootstraps — needs explicit test matrix before flipping the default.

---

## 13. Success Criteria

- A screenshot of Wok is recognizable without the wordmark.
- New users land on the editor surface and discover palette / search / scratch via the status spine within one session.
- Block navigation (rail + `Mod-Up/Down` + search jump) feels equivalent and consistent.
- No regression in first-paint latency or steady-state frame time vs. current build.
- Zero AI affordances visible anywhere in the chrome.
