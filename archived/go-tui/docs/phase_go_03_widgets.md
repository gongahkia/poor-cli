# Phase Go 03 — Widgets

**Priority:** User-facing surface. Every widget is tested in isolation before Wave 5 glues them together.
**Agents:** 5 (all parallel, disjoint files)
**Dependencies:** Wave 2 (theme, config, state)
**Philosophy:** Widgets are pure functions of inputs. State lives in internal/state; theme lives in internal/theme; keybindings live in internal/config. A widget receives all three via constructor injection.

---

## File-scope table

| Agent | Creates | Modifies |
|-------|---------|----------|
| 3A    | `internal/tui/widgets/chat.go`, `internal/tui/widgets/message.go`, `internal/tui/widgets/tool_block.go`, `internal/tui/widgets/chat_test.go` | — |
| 3B    | `internal/tui/widgets/input.go`, `internal/tui/widgets/history.go`, `internal/tui/widgets/input_test.go` | — |
| 3C    | `internal/tui/widgets/statusbar.go`, `internal/tui/widgets/topbar.go`, `internal/tui/widgets/statusbar_test.go` | — |
| 3D    | `internal/tui/widgets/palette.go`, `internal/tui/widgets/commands_registry.go`, `internal/tui/widgets/palette_test.go` | — |
| 3E    | `internal/tui/widgets/mention.go`, `internal/tui/widgets/mention_test.go` | — |

**Zero collisions.** Each agent owns a distinct file set.

---

## Agent 3A: Chat view

### Responsibilities

- Render a scrollable transcript of `state.Message` values.
- Stream updates into the last message via `AppendChunk` without full-widget repaint.
- Respect autoscroll (stick to bottom when user is at bottom; detach when user scrolls up).
- Handle mouse wheel + keyboard scroll.
- Render tool blocks (`state.ToolCall`) as collapsible panels inline in chat.

### Public API

```go
package widgets

type ChatView struct { /* ... */ }

type ChatDeps struct {
    Theme       *theme.Theme
    MDRenderer  markdown.Renderer
    Keymap      *config.Keymap
}

func NewChatView(d ChatDeps) *ChatView
func (c *ChatView) Update(msg tea.Msg) (*ChatView, tea.Cmd)
func (c *ChatView) View(width, height int) string
func (c *ChatView) SetMessages(msgs []state.Message)
func (c *ChatView) AppendChunk(requestID string, chunk string, segs []markdown.Segment)
func (c *ChatView) ScrollUp(n int)
func (c *ChatView) ScrollDown(n int)
func (c *ChatView) ScrollToBottom()
func (c *ChatView) ScrollToTop()
func (c *ChatView) IsAtBottom() bool
```

### Rendering model

Internal representation: `type renderedMsg struct { id string; raw state.Message; blocks []string; totalHeight int }`.

On SetMessages: rebuild all `renderedMsg` from scratch.
On AppendChunk: find the tail `renderedMsg` for the matching requestID; append new segments to its `blocks`; recompute tail height only.

Viewport: `type viewport struct { topIdx int; topOffset int; height int }`. View renders only visible rows.

### Autoscroll

- `IsAtBottom()` returns true if `viewport.topIdx` + `viewport.height` ≥ total rendered rows.
- `AppendChunk` checks IsAtBottom before mutation; if true, ScrollToBottom after mutation.

### Tool block rendering (`tool_block.go`)

ADA-minimal. No boxes. Tool calls render as two muted lines inline in the transcript:

```
▸ bash · git status · 62ms
  └─ args preview (first line, truncated)

when expanded:
▾ bash · git status · 62ms
  args: command=git status
  output:
    On branch main
    nothing to commit, working tree clean
```

Toggle via `enter` / `space` when focus is on that block. No ASCII box drawing — rely on indentation + muted color for hierarchy.

### Tests

1. Stream 100 chunks; assert IsAtBottom remains true; final view matches golden.
2. User scrolls up mid-stream; assert autoscroll detaches; new chunks do not force scroll.
3. Resize 80→120→60; scroll anchor preserved.
4. Long message (10000 chars) renders with correct wrapping.
5. Tool block toggles expand/collapse.

### Acceptance criteria

- [ ] Repaint on chunk append touches only tail blocks.
- [ ] 60 Hz render without jank on 200 tok/s streams (measured in bench package Wave 6D).
- [ ] Mouse wheel events update viewport.
- [ ] All tests pass.

---

## Agent 3B: Input editor

### Responsibilities

- Multi-line text editing with cursor.
- History (up/down arrows) cycling through persisted past submissions.
- Detect leading `/` → emit `PaletteOpenMsg`.
- Detect typed `@` → emit `MentionOpenMsg` with prefix.
- Handle bracketed paste.
- Submit on configured keybind; emit `SubmitMsg{Text}`.

### Public API

```go
type InputField struct { /* ... */ }

type InputDeps struct {
    Theme   *theme.Theme
    Keymap  *config.Keymap
    History *History
}

func NewInputField(d InputDeps) *InputField
func (i *InputField) Update(msg tea.Msg) (*InputField, tea.Cmd)
func (i *InputField) View(width int) string
func (i *InputField) Focus()
func (i *InputField) Blur()
func (i *InputField) Value() string
func (i *InputField) SetValue(s string)
func (i *InputField) Clear()
func (i *InputField) InsertAt(pos int, s string)
func (i *InputField) CursorPos() int
```

### Emitted messages

```go
type SubmitMsg   struct { Text string }
type CancelMsg   struct{}
type PaletteOpenMsg struct { Prefix string }
type MentionOpenMsg struct { Prefix string; CursorPos int }
type MentionCloseMsg struct{}
```

### Edge cases

- Enter alone inserts a newline (multi-line editing); submit requires `ctrl+enter` (configurable).
- Bracketed paste wraps pasted text in `ESC[200~ ... ESC[201~`. Bubbletea exposes these as `tea.KeyMsg` with a specific type; do not interpret as submits.
- History up arrow only when input is empty OR cursor is at start.
- Max input size: 64 KB; reject further input with a toast.

### History (`history.go`)

```go
type History struct {
    entries  []string
    cursor   int   // -1 = no active cycling
    path     string
}
func NewHistory(path string, max int) *History
func (h *History) Push(s string)
func (h *History) Prev() (string, bool)
func (h *History) Next() (string, bool)
func (h *History) Reset()
func (h *History) Save() error
```

Persist to disk on Push. Load on startup. Cap to last 500 entries.

### Tests

1. Typing → value updates; view reflects.
2. Ctrl+Enter emits SubmitMsg; value is cleared; history receives entry.
3. Up arrow at empty → prior history; Down arrow → next.
4. Typing `@` emits MentionOpenMsg with empty prefix; typing more chars updates prefix.
5. Leading `/` on empty input emits PaletteOpenMsg.
6. Bracketed paste with newlines preserved; no accidental submit.
7. Unicode: CJK and emoji cursor positions correct.

### Acceptance criteria

- [ ] History persisted across restarts.
- [ ] Bracketed paste preserves newlines literally.
- [ ] CJK/emoji widths correct via runewidth.

---

## Agent 3C: Status bar & top bar

### Slot order (left → right)

1. Connection dot: ● (green/yellow/red) — from state.Connection.
2. Provider:model — from state.Provider.
3. Session tag — `session:#abcd1234` from state.Session.
4. Context % — from state.ContextPressure with tri-state color.
5. Tokens in/out — from state.Cost.
6. $cost — from state.Cost, CostGood/Warn/Bad color.

### Truncation order (rightmost slots drop first)

If the rendered width exceeds terminal width:
1. Drop tokens display.
2. Drop session tag.
3. Drop context %.
4. Keep conn dot + provider:model + cost always.

### Top bar

Single row above chat: title (app name + version) + breadcrumb (cwd basename · git branch if git repo). No color backdrop — just muted text.

### Tests

1. Width 120 → all slots visible.
2. Width 60 → rightmost slots drop.
3. Truncation is clean — never mid-character.
4. Color changes with cost thresholds.

---

## Agent 3D: Command palette

### Trigger

`PaletteOpenMsg` from input when `/` is typed at empty input or explicit keybind.

### Layout

```
╭─ Commands ───────────────────────────────────╮
│ > /comp                                      │
├──────────────────────────────────────────────┤
│ ▸ /compact     Compact conversation history  │
│   /clear       Clear current conversation    │
│   /cost        Show cost dashboard           │
│   /provider    Switch provider               │
╰──────────────────────────────────────────────╯
```

### Command registry

```go
type Command struct {
    ID          string   // "/compact"
    Label       string
    Description string
    Usage       string   // "/compact [tier]"
    Origin      Origin   // Builtin | Custom
    RequiresArg bool
}

type Registry struct { /* ... */ }
func NewRegistry() *Registry
func (r *Registry) Register(cmds ...Command)
func (r *Registry) Builtins() []Command
func (r *Registry) SetCustoms(cmds []Command)
func (r *Registry) All() []Command
func (r *Registry) Filter(prefix string) []Command
```

Built-in commands are hard-coded. Custom commands arrive via Wave 5B which calls `poor-cli/listCustomCommands`.

### Fuzzy matching

`github.com/sahilm/fuzzy` applied to command ID. Score breakdown:
- Exact prefix match — highest
- Substring match — next
- Fuzzy match — lowest

### Emitted message

```go
type SelectCommandMsg struct { CommandID string; Args string }
```

### Tests

1. `/c` filters to `/compact`, `/clear`, `/cost`.
2. Selection with Enter emits SelectCommandMsg.
3. Escape closes palette; input retains residual "/".
4. Custom commands appear after `SetCustoms`.

---

## Agent 3E: Mention picker

### Trigger

`MentionOpenMsg` from input when `@` is typed.

### Data source

Fetched from state.FileCatalog (populated by Wave 5 via `poor-cli/repoMap` or `poor-cli/contextStatus`).

If catalog is empty on first open: trigger a fetch, show a spinner.

### Layout

```
╭─ @ files ────────────────────────────────────╮
│ @chat.lu                                     │
├──────────────────────────────────────────────┤
│ ▸ nvim-poor-cli/lua/poor-cli/chat.lua         │
│   poor-cli/server/handlers/chat.py            │
│   poor-cli/server/handlers/chat_streaming.py  │
├──────────────────────────────────────────────┤
│ Preview:                                     │
│ local M = {}                                 │
│ function M.open() ...                        │
╰──────────────────────────────────────────────╯
```

### Fuzzy ranking

- Basename match > path match > fuzzy.
- If two files share basename, prefer the one with shorter path.

### Emitted message

```go
type SelectMentionMsg struct { Path string }
```

Handler in Wave 5 inserts `@path` into input and appends path to `contextFiles` of the next chat request.

### Tests

1. `@chat` ranks `chat.lua` and `chat.py` files first.
2. Disambiguation: two `chat.py` files → shorter path wins.
3. Preview loads lazily (first 5 lines).

---

## Decisions locked

- **3A** — Role label rendering: inline prefix (`you`, `poor-cli`) in muted text at the start of each message. No boxes, no background fills. Two blank lines between turns. Code fences keep the muted gutter `│ `.
- **3B** — Max input size: 64 KB. Submit keybind: `Ctrl+Enter`; `Enter` = newline.
- **3C** — Status bar is a single bottom row: `provider:model · $cost`. Always-visible whitelist: provider:model and cost. Everything else (session, context %, tokens) is truncatable and dropped right-to-left on narrow terminals. Top breadcrumb bar: INCLUDED (one row: cwd basename · git branch if repo).
- **3D** — No org-specific builtin commands beyond the standard set.
- **3E** — Preview line count: 5. Fetch preview via `poor-cli/readFile` RPC when available; fall back to direct filesystem read otherwise.
