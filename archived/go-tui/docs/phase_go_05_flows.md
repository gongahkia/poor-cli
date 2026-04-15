# Phase Go 05 — Flows

**Priority:** The wiring wave. Without this, the protocol layer, widgets, and markdown engine are islands. Flows connect them.
**Agents:** 5 (4 fully parallel + 1 follow-on due to collision — see sub-waves)
**Dependencies:** Wave 1 (protocol), Wave 3 (widgets), Wave 4 (markdown)
**Philosophy:** A "flow" is a small orchestrator that subscribes to RPC notifications, mutates state via actions, and emits tea.Msgs for UI. Flows are the only place that combines RPC + state + widgets.

---

## File-scope table

| Agent | Creates | Modifies |
|-------|---------|----------|
| 5A    | `internal/tui/flows/registry.go`, `internal/tui/flows/chat.go`, `internal/tui/flows/chat_test.go` | `internal/tui/app.go` (adds flow hooks) |
| 5B    | `internal/tui/flows/commands.go`, `internal/tui/flows/commands_test.go` | — |
| 5C    | `internal/tui/flows/providers.go`, `internal/tui/flows/sessions.go`, `internal/tui/flows/api_key.go`, `internal/tui/flows/providers_test.go` | — |
| 5D    | `internal/tui/flows/diff.go`, `internal/tui/flows/permissions.go`, `internal/tui/flows/diff_test.go` | — |
| 5E    | `internal/tui/flows/hud.go`, `internal/tui/flows/cost_modal.go`, `internal/tui/flows/hud_test.go` | `internal/tui/app.go` (registers with registry) |

### Intra-phase collisions

- **`internal/tui/app.go`** — 5A (establishes FlowRegistry pattern) and 5E (registers).

### Sub-waves

- **α (serial first):** 5A. Lands FlowRegistry + chat flow. Defines the registration pattern.
- **β (parallel):** 5B, 5C, 5D. Independent.
- **γ (after α):** 5E plugs in via registry with zero diff to app.go beyond adding one `.Register()` call.

---

## FlowRegistry pattern (Agent 5A establishes, everyone uses)

```go
package flows

type Flow interface {
    Name() string
    Start(ctx context.Context, deps Deps) error
    Stop() error
    Update(msg tea.Msg) tea.Cmd  // returns a Cmd or nil; flows consume app.Msg types
}

type Deps struct {
    RPC        *rpc.Client
    Store      *state.Store
    Config     *config.Config
    Keymap     *config.Keymap
    Theme      *theme.Theme
}

type Registry struct {
    flows []Flow
}
func NewRegistry() *Registry
func (r *Registry) Register(f Flow)
func (r *Registry) StartAll(ctx context.Context, d Deps) error
func (r *Registry) StopAll() error
func (r *Registry) UpdateAll(msg tea.Msg) []tea.Cmd
```

In `app.go`:
```go
type Model struct {
    registry *flows.Registry
    // ...widgets
}

func (m Model) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
    cmds := m.registry.UpdateAll(msg)
    // ...also route to widgets
    return m, tea.Batch(cmds...)
}
```

Adding a new flow = one `registry.Register(flows.NewFooFlow(deps))` call in `app.go` Init. No diffs anywhere else.

---

## Agent 5A: Chat send/stream flow

### Responsibilities

1. Listen for `widgets.SubmitMsg` from the input field.
2. Build `protocol.ChatStreamingParams` with `Message`, `ContextFiles`, `RequestID` (new UUID).
3. Append a user Message to state + an empty assistant Message (streaming=true).
4. Launch `rpc.Call(ctx, MethodChatStreaming, params, &result)` in a goroutine.
5. Before the goroutine: subscribe to:
   - `MethodStreamChunk` → `state.ActionAppendChunk`
   - `MethodThinkingChunk` → store for UI indicator
   - `MethodToolEvent` → `state.ActionAppendToolCall`
   - `MethodCostUpdate` → `state.ActionUpdateCost`
   - `MethodProgress` → `state.ActionSetProgress`
6. On Call return:
   - Success → mark assistant message streaming=false.
   - Error → append error toast + finalize message with partial content.
   - Context cancel → send `MethodCancelRequest` notification (not call — fire and forget).
7. Clean up subscriptions.

### Subscription lifecycle

A notification may arrive for a different requestID if multiple turns overlap (shouldn't in v1 but defensively). Filter by `params.requestId == myRequestID`.

### API

```go
package flows

type ChatFlow struct { /* ... */ }
func NewChatFlow(d Deps) *ChatFlow
func (c *ChatFlow) Name() string  { return "chat" }
func (c *ChatFlow) Start(ctx context.Context, d Deps) error
func (c *ChatFlow) Stop() error
func (c *ChatFlow) Update(msg tea.Msg) tea.Cmd
```

### Message types

```go
type StreamStartedMsg  struct { RequestID string }
type StreamChunkMsg    struct { RequestID, Chunk string }
type StreamEndedMsg    struct { RequestID, Reason string; Error error }
```

These are internal — the flow dispatches state actions directly and emits `tea.Msg` only for things the widgets need to know (rare — state subscription covers most cases).

### Cancellation

`widgets.CancelMsg` while streaming → `rpc.Notify(MethodCancelRequest, {requestId})` + `state.Dispatch(ActionCancelInFlight)`. Do NOT wait for a response — the server cancels asynchronously; subsequent stream chunks for that request are ignored by the filter.

### Tests

1. Mock RPC client with scripted notifications; assert state contains expected messages after flow processes them.
2. Cancellation: after 3 chunks, simulate cancel → state shows ended with reason="cancelled".
3. RPC error mid-stream → state shows partial content + error toast action.

### Acceptance criteria

- [ ] `ChatFlow.Start` registers all required subscriptions.
- [ ] `ChatFlow.Stop` unregisters all subscriptions.
- [ ] No goroutine leaks under `goleak`.
- [ ] Race-free under `-race`.

---

## Agent 5B: Slash command handlers

### Command catalog (implement each)

| Command | Action | Server call? |
|---------|--------|--------------|
| /clear | `state.Dispatch(ActionReplaceMessages([]))` | No |
| /compact | summarize+clear via chat turn OR server method if available | `poor-cli/clearHistory` |
| /quit | `tea.Quit` | No |
| /help | open help modal | No |
| /cost | open cost modal | `poor-cli/costSummary` |
| /provider | open provider picker modal | `poor-cli/listProviders` |
| /session | open session picker | `poor-cli/listSessions` |
| /diff | open diff review modal | `poor-cli/listPendingEdits` |
| /watch | toggle watch panel | `watch.status` |

### API

```go
package flows

type CommandsFlow struct { /* ... */ }
func NewCommandsFlow(d Deps) *CommandsFlow
```

### Command execution contract

```go
type CommandExecutor func(args string) tea.Cmd

var executors = map[string]CommandExecutor{
    "/clear":    (*CommandsFlow).cmdClear,
    // ...
}
```

Register custom commands from server:
```go
func (c *CommandsFlow) SyncCustomCommands() tea.Cmd {
    var result protocol.CustomCommandList
    if err := c.rpc.Call(ctx, "poor-cli/listCustomCommands", nil, &result); err != nil {
        return flows.ToastErr("failed to load custom commands: %v", err)
    }
    c.registry.SetCustoms(result.Commands)
    return nil
}
```

Called once at startup; re-called when server sends a `poor-cli/commandsChanged` notification (if such exists) or manually via `/reload-commands`.

### Tests

1. `/clear` empties messages.
3. Server error on switch → toast message.
4. Unknown command → toast "unknown command: /foo".

---

## Agent 5C: Providers, sessions, API key

### Provider picker (modal)

Triggered by `/provider` command.

Layout:
```
╭─ Switch provider ────────────────────────────╮
│ ▸ anthropic        claude-4-6-sonnet  [ready] │
│   openai           gpt-5               [ready] │
│   gemini           gemini-2.5-pro     [ready] │
│   ollama           llama-local         [loc ] │
│   openrouter       auto               [key? ] │
╰──────────────────────────────────────────────╯
```

Fetch: `poor-cli/listProviders` on modal open.
Select: `poor-cli/switchProvider { provider, model }`.
Optimistic UI: immediately update state.Provider; roll back on error.

### Session picker

Triggered by `/session`. Fetch via `poor-cli/listSessions`. Display ordered by UpdatedAt desc. Select → `poor-cli/switchSession { sessionId }` → reload state.

### API key prompt

Flow trigger: `initialize` returned `Capabilities.NeedsAPIKey=true` OR `/provider` switched to an unready provider.

Modal:
```
╭─ API key required: anthropic ────────────────╮
│ Enter API key:                                │
│ ▓▓▓▓▓▓▓▓▓▓▓▓                                 │
│                                               │
│ [x] save to keyring                           │
│                                               │
│ [Enter] save  [Esc] cancel                    │
╰──────────────────────────────────────────────╯
```

On submit: `poor-cli/setApiKey { provider, apiKey, persist: true, reloadActiveProvider: true }`.

**Security**: input field uses concealed mode (echo asterisks). Do not log the key at any level. Clear the buffer on modal close.

### Tests

1. Open provider picker, select provider → RPC call made, state updated.
2. API key rejected by server → modal stays open with error.
3. Concealed field does not leak key to view buffer (assert: rendered view contains asterisks or bullets, not key content).

---

## Agent 5D: Diff review & permissions

### Diff review flow

Trigger: `/diff` command OR `poor-cli/editsReady` notification (server-pushed when the agent completes a round with edits).

Fetch: `poor-cli/listPendingEdits` → list of `PendingEdit{path, hunks}`.

Modal layout:
```
╭─ Pending edits (3) ──────────────────────────╮
│ ▸ internal/foo.go     +14 -3                  │
│   internal/bar.go     +0 -22                  │
│   README.md           +8 -0                   │
╰──────────────────────────────────────────────╯
╭─ Diff: internal/foo.go ──────────────────────╮
│ @@ -1,5 +1,6 @@                               │
│  package foo                                  │
│ +                                             │
│ +import "fmt"                                 │
│ ...                                           │
│                                               │
│ [y] accept hunk  [n] reject  [r] regen         │
│ [Y] accept all   [N] reject all                │
╰──────────────────────────────────────────────╯
```

Actions map to:
- y → `poor-cli/acceptHunk { editId, hunkId }`
- n → `poor-cli/rejectHunk { editId, hunkId }`
- r → `poor-cli/regenerateHunk { editId, hunkId, instruction }` (prompts for optional instruction)
- Y → `poor-cli/acceptAll`
- N → `poor-cli/rejectAll`

Auto-accept rule (if `config.AutoAcceptSafeEdits`): on `editsReady` notification, immediately call `acceptAll` for edits whose `hunks` all have `safetyClass="safe"` (server-provided field if present; otherwise fall back to manual review).

### Permission prompt flow

Trigger: `poor-cli/permissionReq` notification mid-chat-stream.

Modal:
```
╭─ Permission requested ───────────────────────╮
│ Tool: bash                                    │
│ Rationale: install dev dependency             │
│                                               │
│ Command:                                      │
│   npm install -D vitest                       │
│                                               │
│ [A] allow (once)  [S] allow this session      │
│ [P] allow permanently  [D] deny               │
│ [Esc] deny                                    │
╰──────────────────────────────────────────────╯
```

On decision: `rpc.Notify(MethodPermissionRes, { requestId, requestKey, decision, rememberScope })`.

Timeout handling: server may auto-deny after 30s if client does not respond. UI shows a countdown bar.

### Tests

1. Diff list render correct.
2. Accept hunk calls correct RPC.
3. Auto-accept-safe skips modal when all hunks safe.
4. Permission prompt → decision → notification sent.
5. Permission timeout visual indicator works.

---

## Agent 5E: Cost HUD

### Responsibilities

1. Subscribe to `poor-cli/costUpdate` notifications during streaming.
2. Throttle UI updates to 10 Hz (cost notifications can fire per chunk, way faster than needed).
3. Update `state.Cost` via `ActionUpdateCost`.
4. Subscribe to `poor-cli/contextStatus` or periodic `poor-cli/getContextPressure` (every 5s during idle, more often during streaming) → update `state.ContextPressure`.
5. On `/cost` command, open a detailed modal.

### Throttle implementation

```go
type HudFlow struct {
    lastCostPaint time.Time
    pendingCost   *protocol.CostSnapshot
}

func (h *HudFlow) onCostUpdate(raw json.RawMessage) {
    var cu protocol.CostUpdate
    _ = json.Unmarshal(raw, &cu)
    h.pendingCost = cu.ToSnapshot()
    if time.Since(h.lastCostPaint) > 100*time.Millisecond {
        h.flush()
    } else {
        // schedule flush on next tick
    }
}
```

Registry sends a `tea.Tick(100ms)` for the throttle; on each tick, flush pending if any.

### /cost modal

Detailed layout:
```
╭─ Cost this session ──────────────────────────╮
│ Current turn:     $0.0083                     │
│ Session total:    $0.0472                     │
│                                               │
│ Tokens:                                       │
│   Input:          12,834                      │
│   Output:         2,104                       │
│   Cache read:     8,222                       │
│   Cache write:    4,190                       │
│                                               │
│ By provider:                                  │
│   anthropic       $0.0412                     │
│   openai          $0.0060                     │
│                                               │
│ Savings (economy mode): $0.0134 (22%)         │
╰──────────────────────────────────────────────╯
```

Fetch: `poor-cli/costSummary` on modal open + `poor-cli/savingsSnapshot`.

### Tests

1. 100 costUpdate notifications within 100ms → only 1 state dispatch.
2. `/cost` modal fetches and renders.
3. Context pressure crossing 80% triggers toast warning.

---

## Integration checklist

By end of Wave 5, the following user journeys must work end-to-end:

1. **Happy path chat**: user types message → submits → sees streaming response with markdown + code highlighting → cost updates live in status bar → response finalizes.
2. **Cancel**: user presses ctrl+c mid-stream → in-flight state cleared → cancel notification sent → partial response retained.
3. **Slash command**: user types `/provider` → modal opens with list → selects → provider switched → status bar updates.
4. **File mention**: user types `@chat.lua` → picker opens → selects → path inserted → next chat includes file as context.
5. **Diff review**: agent produces edits → diff modal opens → user accepts/rejects each hunk → files on disk change.
6. **Permission prompt**: agent wants to run risky tool → modal → user allows once → tool runs → continues streaming.
7. **Startup with missing API key**: server returns needsApiKey → API key modal → user enters key → server accepts → chat available.

Wave 6A writes the end-to-end test that exercises (1), (2), and (3).

---

## Decisions locked

- **5A** — Auto-scroll during stream: YES when user is at the bottom; detaches when user scrolls up.
- **5B** — No custom commands beyond the standard set.
- **5C** — Default provider at startup: reads from `config.DefaultProvider` (Apache-2.0 defaults ship `anthropic`). Picker SHOWS unready providers with a muted `[not ready]` suffix so users can select and be prompted for keys.
- **5D** — Auto-accept threshold: safe-only when `config.AutoAcceptSafeEdits = true` (DEFAULT ON per project decisions). Hunks missing a `safetyClass` from the server always require manual review.
- **5E** — Cost alert thresholds: $0.05/completion warns yellow; $0.25/completion warns red.
