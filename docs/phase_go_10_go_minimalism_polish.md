# Phase Go 10 — Go Client Minimalism Polish

**Priority:** Last ship-gate for the Go TUI. Every earlier wave can leak chrome unintentionally — this wave hunts and removes it.
**Agents:** 3 (all parallel, disjoint concerns)
**Dependencies:** Waves 5, 6, 9 must have landed. W10 runs after the Go client is feature-complete.
**Philosophy:** ADA-minimal is a discipline, not a style. Anything that can be hidden, removed, or condensed should be. The benchmark question at every review: *"If I deleted this pixel, would a user notice?"* If no → delete.

---

## Target aesthetic

The Go client must feel like ADA:

- Blank background. No borders, no dividers, no box-drawing around chat content.
- Two colors of text in steady state: base and muted.
- No redundant labels ("user:", "assistant:" become `you ›`, `poor-cli ›`).
- Bottom status line is ≤1 row. Top breadcrumb is ≤1 row. Nothing else is permanent.
- Transitions between turns = one blank row. Not a rule, not a line, not a separator glyph.
- Splash is a single line for 500ms max: `gocli-poor · connecting…`.

Reference visual (final):

```
  gocli-poor · poor-cli · main

  you ›  write me a haiku

  poor-cli ›  autumn wind arrives
              scattering leaves across
              the cold morning path

  you ›  _
  anthropic · $0.01
```

Nothing more. If the current client renders more, this wave removes it.

---

## File-scope table

| Agent | Creates | Modifies |
|---|---|---|
| 10A | `docs/visual_audit.md` (living doc) | any widget in `internal/tui/widgets/` or `internal/theme/` that fails the audit |
| 10B | `bench/perceived_latency_test.go` | `internal/tui/app.go` (render cadence), `internal/markdown/renderer.go` (commit flush) |
| 10C | `internal/tui/empty_states.go`, `internal/tui/empty_states_test.go` | any flow in `internal/tui/flows/` that currently shows a stub or loader |

### Intra-phase collisions

Low. 10A audits + makes surgical edits across multiple files but does not add new files. 10B touches app.go's render loop. 10C adds empty-state rendering in flows.

If 10A and 10B happen to touch the same widget (e.g. status bar), 10A lands first (visual truth), then 10B tunes its cadence.

### Proposed sub-waves

- **α (parallel):** 10A + 10C.
- **β (serial, after α):** 10B. Cadence tuning benefits from the finalized widget shapes.

---

## Agent 10A: Visual audit and chrome strip

### Goal

Walk every user-visible surface. For each, decide if it is ADA-minimal compliant. If not, edit it.

### Method

1. Build and run the client locally with a mock server that replays `test/fixtures/chat-session-01.jsonl`.
2. Screenshot each of these states (save to `docs/audit/` as ASCII captures):
   - Splash
   - Empty chat (no messages yet)
   - First user turn in flight
   - Streaming assistant response mid-stream
   - Completed turn
   - Three-turn transcript
   - Command palette open
   - Mention picker open
   - Provider picker modal
   - Session picker modal
   - Diff review modal (single hunk)
   - Diff review modal (multiple hunks)
   - Permission prompt
   - API key prompt
   - Cost modal (/cost)
   - Users panel open (if multiplayer enabled)
   - Error toast
   - Success toast
   - Resize to 60 cols
   - Resize to 200 cols
3. For each capture, score against the ADA-minimal checklist:
   - [ ] No box-drawing except absolute necessity (modals may have ≤1 border; chat area may not).
   - [ ] No filled backgrounds on content.
   - [ ] Colors limited to Base, Muted, Focus, Success, Error, Warning (6 tokens total).
   - [ ] Every label is ≤16 chars and ≤1 line.
   - [ ] No emoji.
   - [ ] No icons other than `●`, `◌`, `›`, `·`, `✓`, `✗`.
   - [ ] Chat message gap is exactly one blank line.
   - [ ] No "section" headers inside panels (no `── Commands ──` titles).
4. For each failure, edit the responsible file to bring it into compliance. Record the edit in `docs/visual_audit.md`.

### Specific known offenders to check and fix

These elements were sketched in earlier phase docs using Codex-style chrome. The audit must confirm and correct:

- **Tool block rendering** (phase_go_03 Agent 3A): earlier spec used `╭─ args ─╮` boxes. ADA-minimal replacement (already patched in W3 decisions): simple indentation + muted labels.
- **Command palette** (phase_go_03 Agent 3D): shown with `╭─ Commands ─╮` header. Strip to no header; list only.
- **Mention picker** (phase_go_03 Agent 3E): shown with border + section for preview. Strip border; preview is a single row below the list, muted.
- **Users panel** (phase_go_09 Agent 9A): verify no border, flush with transcript.
- **Diff review modal** (phase_go_05 Agent 5D): the existing sketch used `╭─ Pending edits ─╮`. Replace with a flush header row `pending edits · 3` and no border.
- **Permission modal**: same — flush header, no border.

### New widget helpers

If a flush-style pattern is repeated, consolidate into `internal/tui/widgets/flush.go`:

```go
package widgets

type Flush struct { /* ... */ }

// FlushHeader returns a single muted line to introduce a region, no border.
func FlushHeader(theme *theme.Theme, label string) string

// FlushList renders a list without borders, one item per line with 2-space left pad.
func FlushList(theme *theme.Theme, items []string, selectedIdx int) string
```

Every modal consumes Flush helpers.

### Deliverables

1. `docs/visual_audit.md` — ASCII snapshots of all audited states + red-yellow-green checklist per state + diff of changes made.
2. Code edits across widget files to strip non-compliant chrome.
3. `internal/tui/widgets/flush.go` if consolidation is warranted.
4. Updated golden snapshots for every affected widget test.

### Acceptance criteria

- [ ] Every audited state passes the ADA-minimal checklist.
- [ ] `docs/visual_audit.md` exists and is checked in.
- [ ] No new color tokens introduced.
- [ ] Golden snapshots updated and CI is green.

---

## Agent 10B: Perceived latency polish

### Goal

The client must feel instant. Users should not perceive render lag even on modest hardware.

### Targets (measured via `bench/perceived_latency_test.go`)

| Metric | Target |
|---|---|
| Keystroke → on-screen echo | ≤ 8 ms |
| First byte of stream → visible text | ≤ 16 ms |
| Render frame duration at 200 tok/s stream | ≤ 8 ms |
| Render cadence (steady) | 60 Hz |
| Splash-to-first-paint | ≤ 150 ms |

### Method

1. Write a harness that drives bubbletea with a scripted message stream at controlled rates (50, 100, 200 tok/s).
2. Instrument `app.go` Update/View with nanosecond timestamps logged to a trace file.
3. Profile with pprof. Identify any hot path > 1 ms.
4. Apply fixes:
   - Coalesce renders to 60 Hz tick (Bubbletea already does this; verify no extra renders are triggered).
   - Cap markdown renderer tail-paint work per frame: if the tail has more than N segments, split across frames.
   - Ensure state.Snapshot() does not copy more than necessary (e.g. do not copy full message bodies for HUD updates).
   - Ensure keystroke echo is synchronous; no deferred paint.

### Specific optimizations to implement if profiling shows them

- **Render-on-demand**: if no state has changed since the last paint, skip the tea.Cmd entirely (check a dirty flag).
- **Segment reuse**: markdown renderer reuses slices for tail paint rather than re-allocating.
- **Dirty-rect mentality**: chat view tracks `lastRenderedBottom` and only asks markdown renderer for `TailSince(bottom)`.

### Deliverables

1. `bench/perceived_latency_test.go` measuring all five metrics.
2. Performance report in `docs/perceived_latency.md` with before/after numbers and flamegraph links.
3. Any source edits needed to hit targets.

### Acceptance criteria

- [ ] All five metrics hit target on reference hardware (M-series laptop).
- [ ] No regression in existing benchmarks.
- [ ] Trace logs can be enabled via `GOCLI_POOR_TRACE=1` env var and written to `$XDG_STATE_HOME/gocli-poor/trace.jsonl`.

---

## Agent 10C: Empty states and loading affordances

### Goal

Every state the user can reach must show a sensible, minimal thing — not a blank screen or a spinner. Every loading moment is either instant (no indicator) or a one-line muted hint.

### States to define

1. **Fresh launch, no messages yet**:
   ```
   gocli-poor · connected · anthropic

   ready.
   ```
   "ready." is the only content, muted, one blank line below the breadcrumb.

2. **Connecting to server**:
   ```
   gocli-poor · connecting…
   ```
   No spinner. No progress bar.

3. **Server crashed / disconnected**:
   ```
   gocli-poor · disconnected — press ctrl+r to retry
   ```
   Error-token accent on "disconnected".

4. **No providers available (needs API key)**:
   ```
   gocli-poor · anthropic needs an API key · press / for commands
   ```

5. **Waiting for response (before first chunk)**:
   Keep the `poor-cli ›` prefix visible with a muted blinking cursor immediately after the `›`. No spinner glyph. No "thinking…" label.

6. **Streaming in progress**:
   No extra indicator. The text appears; that is the indicator.

7. **Cancelled mid-stream**:
   ```
   poor-cli ›  (partial response…)
               — cancelled
   ```
   The "— cancelled" hint is muted, on its own indented line after the partial response.

8. **Empty diff review (no edits)**:
   ```
   pending edits · none
   ```

9. **Empty session list**:
   ```
   sessions · none yet
   ```

10. **Multiplayer: room empty**:
    ```
    users · just you
    ```

### Implementation

Create `internal/tui/empty_states.go`:

```go
package tui

type EmptyState struct {
    Key   string   // identifies which state
    Text  string
}

func EmptyStateFor(key string, data ...any) EmptyState
```

Each flow/widget that has a possible empty state resolves it via this helper, guaranteeing consistency.

### Deliverables

1. `internal/tui/empty_states.go` with every empty-state entry.
2. Edits to flows/widgets to use the helper (remove any ad-hoc "Loading..." or "None found" strings).
3. `internal/tui/empty_states_test.go` verifying each state renders correctly.

### Acceptance criteria

- [ ] Every listed state has a defined, tested empty string.
- [ ] No spinner, progress bar, or animated indicator anywhere in the client.
- [ ] Empty-state text is always ≤1 line and always muted.

---

## Wave completion gates

Before declaring W10 done, confirm:

- [ ] A first-time user launching the binary sees the "ready." empty state, not a blank screen.
- [ ] Side-by-side comparison of a chat session against the ADA reference (captured as ASCII in `docs/visual_audit.md`) shows ≤5% visual difference by manual review.
- [ ] `docs/visual_audit.md` is up to date and covers all 20+ states from Agent 10A.
- [ ] All three perceived-latency targets hit.
- [ ] Zero boxes anywhere in the chat transcript or streaming response region.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| Audit is subjective and reviewer-dependent | Ship the ADA reference ASCII alongside the audit doc; compare directly |
| Perf tuning introduces regressions | All changes go through bench suite in CI; >10% regression fails the build |
| Empty-state consolidation breaks existing tests | Update golden snapshots as part of this wave; do not defer |

## Acceptance criteria (wave-level)

- [ ] Visual audit document committed and every state passes.
- [ ] Performance report committed and every target hit.
- [ ] Every flow/widget uses `EmptyStateFor(...)` for empty conditions.
- [ ] Manual acceptance: user with no prior exposure to the project loads the binary, chats for 5 minutes, reports "this feels fast and simple" or equivalent.
