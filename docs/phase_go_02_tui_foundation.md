# Phase Go 02 — TUI Foundation

**Priority:** Critical path for UX. Produces the frame every widget plugs into.
**Agents:** 4 (all parallel, disjoint packages)
**Dependencies:** Wave 0
**Philosophy:** Elm-style. Pure Update/View. Put every side effect behind a tea.Cmd. Every color behind a theme token.

---

## File-scope table

| Agent | Creates | Modifies |
|-------|---------|----------|
| 2A    | `internal/tui/app.go`, `internal/tui/messages.go`, `internal/tui/focus.go`, `internal/tui/regions.go`, `internal/tui/modal.go`, `internal/tui/app_test.go` | `internal/tui/doc.go` |
| 2B    | `internal/theme/theme.go`, `internal/theme/dark.go`, `internal/theme/light.go`, `internal/theme/loader.go`, `internal/theme/caps.go`, `internal/theme/theme_test.go` | `internal/theme/doc.go` |
| 2C    | `internal/config/config.go`, `internal/config/load.go`, `internal/config/defaults.go`, `internal/config/keys.go`, `internal/config/config_test.go` | `internal/config/doc.go` |
| 2D    | `internal/state/store.go`, `internal/state/types.go`, `internal/state/actions.go`, `internal/state/reducer.go`, `internal/state/store_test.go` | `internal/state/doc.go` |

### Intra-phase collisions

**None.** Fully disjoint.

---

## Agent 2A: Bubbletea app shell

### Screen regions

```
┌──────────────────────────────────────────┐  ← TopBar (1 row)
│ gocli-poor · repo:poor-cli · branch:main │
├──────────────────────────────────────────┤  ← ChatView (h - 5)
│                                          │
│   (scrollable transcript)                │
│                                          │
├──────────────────────────────────────────┤  ← Input (3–10 rows, autosize)
│ > prompt here                            │
├──────────────────────────────────────────┤  ← StatusBar (1 row)
│ ● anthropic:claude-4-6 · 12%ctx · $0.03 │
└──────────────────────────────────────────┘

Overlaid when active:
- Command palette (center, ~40% height)
- Mention picker (attached to input cursor)
- Modal (provider picker, diff review, permission prompt)
```

### Messaging contract

Every widget communicates via tea.Msg. Cross-cutting messages live in `messages.go`:

```go
package tui

type ResizeMsg struct { Width, Height int }
type SwitchFocusMsg struct { Target FocusTarget }
type OpenModalMsg struct { Kind ModalKind; Payload any }
type CloseModalMsg struct{}
type ToastMsg struct { Kind ToastKind; Text string; TTL time.Duration }
type FocusTarget int
type ModalKind int
```

### Lifecycle

- `Init()` → returns `tea.Batch(state.Subscribe(), tea.EnterAltScreen)` plus a connect Cmd that Wave 1D's Manager produces via Wave 5A wiring.
- `Update(msg)` → routes by focus target; modal stack intercepts all events when non-empty.
- `View()` → joins regions; overlays modal via `lipgloss.Place`.

### Focus router (`focus.go`)

Enum: `FocusInput`, `FocusChat`, `FocusModal`. Keymap lookups dispatch to the owning widget. Non-owned keys fall through to global actions (quit, switch focus, open palette).

### Modal stack (`modal.go`)

`type ModalStack []Modal` with `Push`, `Pop`, `Top`, `Len`. Rendering: stack is rendered bottom-up over the content; only the top modal receives input.

### Tests

Use `github.com/charmbracelet/x/exp/teatest`. Minimum scenarios:
1. Resize preserves chat scroll anchor.
2. Pressing `/` at empty input opens palette modal.
3. Escape on open modal closes it.
4. Typing in input when modal is open goes to modal, not input.

### Acceptance criteria

- [ ] app.go < 400 LOC.
- [ ] All tests pass.
- [ ] No direct imports of internal/rpc, internal/server, or internal/protocol from `app.go` (only through state).
- [ ] Screen redraw is flicker-free across resize (manual check).

---

## Agent 2B: Theme & styles

### Token list (complete)

```
Base            default text
Muted           dimmed text
Border          box borders
Focus           focused element accent
Error, Success, Warning, Info  toasts and status
ChatUser        user role
ChatAssistant   assistant role
ChatTool        tool_call role
ChatSystem      system messages
ChatCode        inline code
ChatLink        links
StatusBar       default status bar cells
StatusBarActive highlighted status cell
TopBar          top bar background
InputField      default input border
InputFieldFocused  focused input border
Modal           modal background / border
ModalTitle      modal title bar
Palette, PaletteHighlight  command palette list + selected
MentionList, MentionHighlight  mention picker list + selected
CostGood, CostWarn, CostBad  cost HUD tri-state
ToolPending, ToolSuccess, ToolError  tool-call badges
```

### YAML loader

```yaml
name: "my-theme"
inherits: "dark"          # "dark" | "light" | path
styles:
  chat_user:
    foreground: "#00ffff"
    bold: true
  border:
    foreground: "240"
```

Any unspecified token inherits from `inherits`. `foreground`/`background` accept hex (`#RRGGBB`), ANSI 0–15 names, or 0–255 palette numbers.

### Capability detection

- `NO_COLOR` set → monochrome theme (no color escapes).
- `COLORTERM=truecolor` or `24bit` → full truecolor.
- `TERM=xterm-256color` → 256-color fallback.
- Else → 16-color fallback.

### Tests

Golden outputs per token rendered to a fixed-width string. Diff against committed fixtures.

### Acceptance criteria

- [ ] Every token is defined in both dark and light themes.
- [ ] Loader merges partial user themes without losing tokens.
- [ ] NO_COLOR produces zero ANSI escapes.
- [ ] No raw `lipgloss.Color(...)` calls exist outside internal/theme/.

---

## Agent 2C: Config & keybindings

### Config schema (YAML)

```yaml
theme: dark
server_path: ""
default_provider: anthropic
default_model: claude-4-6-sonnet
context_budget_tokens: 180000
max_response_tokens: 8192
auto_accept_safe_edits: false
history_file: ~/.local/share/gocli-poor/history
log_level: info
keybindings:
  submit: ctrl+enter
  cancel: ctrl+c
  palette: /
  mention: "@"
  focus.chat: ctrl+j
  focus.input: ctrl+i
  scroll.up: pgup
  scroll.down: pgdn
  scroll.top: home
  scroll.bottom: end
  accept.edit: ctrl+y
  reject.edit: ctrl+n
  regen.edit: ctrl+r
  quit: ctrl+q
```

### Path resolution

1. `$XDG_CONFIG_HOME/gocli-poor/config.yaml`
2. `~/.config/gocli-poor/config.yaml`
3. `~/.gocli-poor.yaml`

First hit wins. Missing → defaults only.

### Env var overrides

Prefix `GOCLI_POOR_`. Snake-case of YAML path. Example: `GOCLI_POOR_DEFAULT_PROVIDER=openai`.

### Keymap compilation

```go
type Keymap struct {
    Submit         key.Binding
    Cancel         key.Binding
    Palette        key.Binding
    Mention        key.Binding
    FocusChat      key.Binding
    FocusInput     key.Binding
    ScrollUp       key.Binding
    ScrollDown     key.Binding
    ScrollTop      key.Binding
    ScrollBottom   key.Binding
    AcceptEdit     key.Binding
    RejectEdit     key.Binding
    RegenEdit      key.Binding
    Quit           key.Binding
}

func (k *Keymap) FromConfig(c *Config) error
```

String → key.Binding uses Bubbletea's `key.NewBinding(key.WithKeys(...))`. Validate against a known list; error on unknown keys.

### Tests

1. Precedence: XDG > default.
2. Env override applied.
3. Partial config merges with defaults.
4. Unknown keybinding → validation error with helpful message.

### Acceptance criteria

- [ ] Adding new config fields is backward-compatible.
- [ ] Every default action has a keybinding defined.
- [ ] Validation errors cite the file + line if possible.

---

## Agent 2D: App state store

### Central types

```go
package state

type AppState struct {
    Messages        []Message
    InFlight        *InFlight
    Provider        ProviderState
    Cost            CostState
    Session         SessionState
    Connection      ConnState
    ContextPressure ContextPressure
    Toasts          []ToastItem
}

type Message struct {
    ID          string
    Role        Role              // User | Assistant | Tool | System
    Content     string
    Segments    []MarkdownSegment // pre-rendered by markdown.Streamer
    RequestID   string
    Streaming   bool
    ToolCalls   []ToolCall        // attached tool events if any
    CreatedAt   time.Time
}

type InFlight struct {
    RequestID string
    StartedAt time.Time
    CancelFn  func()
}

type ConnState struct {
    Phase     ConnPhase  // Disconnected, Starting, Ready, Error
    LastError string
}
```

### Store

```go
type Store struct {
    mu       sync.RWMutex
    state    AppState
    actions  chan Action
    subs     []chan AppState
}

func NewStore() *Store
func (s *Store) Snapshot() AppState
func (s *Store) Dispatch(a Action)
func (s *Store) Subscribe() (<-chan AppState, func())
func (s *Store) Run(ctx context.Context) error  // consumes actions, applies reducer
```

Dispatcher semantics:
- One goroutine runs the reducer loop (`Run`).
- Actions are sent via channel; reducer is pure.
- Subscribers receive a `AppState` snapshot after every dispatch.
- Snapshot is a deep-ish copy (slices copied; nested maps by reference OK since actions replace not mutate).

### Action types

```go
type Action interface { actionMarker() }

type ActionAppendMessage    struct { Msg Message }
type ActionStartStream      struct { RequestID string; AssistantMsgID string }
type ActionAppendChunk      struct { RequestID string; Chunk string; Segments []MarkdownSegment }
type ActionEndStream        struct { RequestID string; Reason string }
type ActionSetProvider      struct { Info ProviderInfo }
type ActionUpdateCost       struct { Snapshot CostSnapshot }
type ActionSetConnection    struct { Phase ConnPhase; Err string }
type ActionToast            struct { Kind ToastKind; Text string; TTL time.Duration }
type ActionReplaceMessages  struct { Messages []Message }
type ActionUpdateContextPressure struct { Pressure ContextPressure }
type ActionCancelInFlight   struct{}
```

Each has an empty `actionMarker()` so the interface is closed.

### Reducer rules

- Reducer is one `switch` over action type.
- Each case returns a new `AppState`. Do not mutate the input.
- Pre-allocate common result shapes; avoid reallocating `Messages` slice when appending (use `append` which handles growth, or a capped ring buffer if memory is a concern).

### Tests

1. `ActionAppendChunk` during streaming merges into the last message.
2. `ActionAppendMessage` creates a new message.
3. `ActionCancelInFlight` clears InFlight pointer.
4. 1000 concurrent Dispatch calls converge to a consistent state.
5. Subscribers receive every snapshot; no skips.
6. Store.Close stops the reducer goroutine cleanly.

### Acceptance criteria

- [ ] `go test -race` clean.
- [ ] No goroutine leaks.
- [ ] Reducer is 100% pure (no time/net/rand inside).
- [ ] Snapshot copies prevent external mutation of internal state.

---

## Decisions locked

- **2A** — Splash screen: INCLUDED. Add an `IntroModel` focus target that renders a one-line "gocli-poor vX.Y.Z · connecting…" for up to 500ms during startup or until the first successful `initialize` response, whichever comes first. No logo art, no progress bar.
- **2B** — Palette is ADA-minimal dark. Accent `#89b4fa` (cool blue), muted `#585858`, warning `#f9e2af`, error `#f38ba8`, success `#a6e3a1`. No background fills on chat blocks. Light theme mirrors the dark hues at higher luminance. Monochrome fallback strips all ANSI colors and uses bold/dim for emphasis only.
- **2C** — Ship the default keybindings as given. Submit = `Ctrl+Enter`; `Enter` = newline.
- **2D** — Max-messages threshold: 1000.
