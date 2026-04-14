# Orchestration — Go TUI Client for poor-cli

Master orchestration document for parallel agent execution across 11 waves that deliver:

1. a standalone Go TUI chat client (working title: `gocli-poor`) with ADA-minimal look — waves 0–6 and 10;
2. a multiplayer backend robustness upgrade (Python server) — wave 7;
3. multiplayer UI for the existing Neovim plugin — wave 8;
4. multiplayer UI for the new Go client — wave 9.

The Go client plugs into the existing `poor-cli-server --stdio` JSON-RPC backend; waves 0–6 and 10 require **zero server-side changes**. Waves 7–9 extend the server and both frontends together.

Total agents across all waves: **40**. Maximum parallel agents in a single wave: **5**.

Each wave contains copy-paste-ready prompts per agent. Prompts reference the corresponding `phase_go_XX_*.md` document for full implementation details.

---

## Project goal

Build a standalone Go binary that:
- spawns `poor-cli-server --stdio` as a child process
- speaks LSP-style framed JSON-RPC (`Content-Length: N\r\n\r\n` + UTF-8 JSON)
- renders a multi-pane TUI comparable visually to Clockwork, Codex CLI, and ADA
- streams markdown with zero flicker via a custom incremental tokenizer (not Glamour)
- ships as a single static binary via goreleaser

**No server-side changes.** The Python backend is transport-agnostic already. Every capability is reached through the same JSON-RPC surface the Neovim Lua plugin uses today.

**Reference client:** `nvim-poor-cli/lua/poor-cli/rpc.lua` and `chat.lua` — the working Lua implementation is the ground truth for message shapes and flow.

---

## Reading guide

- **Waves are partially ordered** — see dependency graph below; not every wave is strictly sequential.
- **Agents within a wave are parallel** unless a collision is noted in that wave's doc.
- **Prompts are ready-to-run** — all design decisions have been resolved in the phase docs; no marker substitution is required.
- **Each prompt references a phase doc** — the agent should read that doc first for full context.
- **Each prompt is self-contained** — assume the agent has zero prior context; the prompt + phase doc together are complete.

---

## Dependency graph

```
W0 (bootstrap)
  │
  ├──> W1 (protocol)         ─┐
  │                            ├──> W5 (flows) ──┬──> W6 (polish & ship)
  ├──> W2 (tui foundation) ──> W3 (widgets) ─┤   │
  │                                            │   └──> W9 (multiplayer Go) ──┐
  └──> W4 (streaming markdown) ────────────────┘                               │
                                                                               ├──> W10 (Go minimalism polish)
W7 (multiplayer backend, independent) ──┬──> W8 (multiplayer Neovim)           │
                                         │                                      │
                                         └──> W9 (multiplayer Go) ──────────────┘
```

- **W1 ⊥ W2 ⊥ W4** — fully independent, can all run in parallel after W0.
- **W3** blocks on W2 only.
- **W5** blocks on W1 + W3 + W4.
- **W6** blocks on W5.
- **W7** is independent of the Go client waves — it modifies the Python backend only and can run in parallel with W0–W6.
- **W8** blocks on W7.
- **W9** blocks on W5 (Go client must have a working chat flow) AND W7 (backend features must exist).
- **W10** blocks on W9 (polish runs last, after the Go client is feature-complete).

**Fast path** (4 agent sessions running in parallel):
1. Session A: W0 → W1 → W5 → W6 → W9 → W10
2. Session B: wait for W0 → W2 → W3 → W5 → W9 (widgets + flows shared work)
3. Session C: wait for W0 → W4 → W6 (markdown + benchmarks)
4. Session D: W7 (Python-only) → W8 (Neovim) — runs independently from the moment W7 is green

---

## Wave overview

| Wave | Name | Agents | Parallelism | Blocks on | Est. days |
|------|------|--------|-------------|-----------|-----------|
| 0 | Bootstrap | 1 | serial | — | 0.5 |
| 1 | Protocol layer | 4 | all parallel | W0 | 2–3 |
| 2 | TUI foundation | 4 | all parallel | W0 | 2–3 |
| 3 | Widgets | 5 | all parallel | W2 | 3–5 |
| 4 | Streaming markdown | 4 | 4A∥4B∥4D; 4C serial | W0 | 3–5 |
| 5 | Flows | 5 | 4 parallel + 1 serial | W1+W3+W4 | 3–5 |
| 6 | Polish & ship | 4 | all parallel | W5 | 2–3 |
| 7 | Multiplayer backend | 4 | 3 parallel + 1 serial | — (Python-only) | 3–5 |
| 8 | Multiplayer Neovim | 3 | all parallel | W7 | 2–3 |
| 9 | Multiplayer Go | 3 | all parallel | W5+W7 | 2–3 |
| 10 | Go minimalism polish | 3 | 2 parallel + 1 serial | W9 | 2–3 |

**Total span** if linearised: ~30 days. **Total span** with 4-session parallelism: ~13–15 days.

---

## Directory layout (produced by W0)

```
gocli-poor/
├── cmd/gocli-poor/main.go              # entry point
├── internal/
│   ├── transport/                       # W1A — framed stdio codec
│   ├── rpc/                             # W1B — JSON-RPC client
│   ├── protocol/                        # W1C — Go structs for all messages
│   ├── server/                          # W1D — child process lifecycle
│   ├── tui/                             # W2A — Bubbletea root
│   │   ├── widgets/                     # W3A–E — chat, input, statusbar, palette, mention
│   │   └── flows/                       # W5A–E — chat, commands, diff, permissions, hud
│   ├── theme/                           # W2B
│   ├── config/                          # W2C
│   ├── state/                           # W2D
│   └── markdown/                        # W4 — streaming tokenizer + renderer
├── docs/                                # user-facing
├── test/                                # integration
├── go.mod
├── Makefile
├── .goreleaser.yml
└── README.md
```

Every file path in phase docs assumes this layout.

---

## Wave 0 — Bootstrap

**Agents: 1 (serial — blocks everything)**
**Reference document:** `docs/phase_go_00_bootstrap.md`
**Estimated time:** 4–8 hours
**Prerequisites:** None

### Agent 0A — Repo scaffold

```
[AGENT PROMPT — copy/paste to your coding agent]

You are bootstrapping a greenfield Go project that will become a TUI chat client
for the existing poor-cli Python JSON-RPC server. This wave is pure scaffolding —
no business logic. Every later wave builds on the layout you produce.

FIRST: Read docs/phase_go_00_bootstrap.md for full details and acceptance criteria.

CONTEXT:
- The Go client lives in a new directory at `/Users/gongahkia/Desktop/coding/projects/gocli-poor`, alongside `poor-cli`.
- The Python backend already exists at /Users/gongahkia/Desktop/coding/projects/poor-cli and does NOT need changes.
- Reference implementation to match feature parity: nvim-poor-cli/lua/poor-cli/rpc.lua + chat.lua.
- Go version target: 1.22+.
- Dependencies to pin in go.mod: github.com/charmbracelet/bubbletea, github.com/charmbracelet/lipgloss, github.com/charmbracelet/bubbles, github.com/alecthomas/chroma/v2, github.com/mattn/go-runewidth, github.com/sahilm/fuzzy, github.com/zalando/go-keyring, gopkg.in/yaml.v3.

YOUR DELIVERABLES:
1. Create the directory tree exactly as specified in the orchestration doc "Directory layout" section.
2. go.mod with the dependency pins listed above.
3. cmd/gocli-poor/main.go — a placeholder main that prints "gocli-poor vX.Y.Z" and exits 0.
4. Makefile with targets: build, test, lint, run, fmt, clean, release.
5. .goreleaser.yml skeleton for cross-platform builds (darwin/linux/windows, amd64/arm64).
6. .github/workflows/ci.yml running: go vet, golangci-lint, go test ./..., make build.
7. README.md stub — one paragraph describing the project + link to orchestration.md.
8. LICENSE file — Apache-2.0.
9. .gitignore covering Go, macOS, editors.
10. A `VERSION` file containing "0.0.1".

CONSTRAINTS:
- Do NOT implement any transport/TUI/logic yet — later waves own that.
- Do NOT add dependencies beyond the list above without justification in a comment.
- Make every package directory compile (empty doc.go if nothing else).
- CI must pass on green.
- No organization-specific CI modifications required.

Read the phase doc first, then implement.
```

---

## Wave 1 — Protocol Layer

**Agents: 4 (all parallel)**
**Reference document:** `docs/phase_go_01_protocol.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W0

Intra-wave collisions: **none**. Each agent owns a disjoint package directory.

### Agent 1A — Framed stdio transport codec

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the LSP-style Content-Length framing codec for the Go TUI
client. This is the lowest layer: bytes on a pipe → framed messages, and back.

FIRST: Read docs/phase_go_01_protocol.md, specifically the "Agent 1A" and
"Framing" sections. Exact byte rules, encoding, and compatibility notes are there.

CONTEXT:
- Reference implementation (Python): /Users/gongahkia/Desktop/coding/projects/poor-cli/poor_cli/server/transport.py — study lines 62–213.
- Reference implementation (Lua): /Users/gongahkia/Desktop/coding/projects/poor-cli/nvim-poor-cli/lua/poor-cli/rpc.lua lines 1240–1321.
- Framing rule: `Content-Length: <bytes>\r\n\r\n<utf-8 json>`. Header is ASCII. Body byte count must match UTF-8 encoded body length exactly.
- The server also tolerates `\n\n` separator as fallback. Match this on the reader side.

YOUR DELIVERABLES:
1. internal/transport/codec.go — exported Reader and Writer types wrapping io.Reader / io.Writer.
   - NewReader(r io.Reader) *Reader; (r *Reader).ReadMessage() ([]byte, error)
   - NewWriter(w io.Writer) *Writer; (w *Writer).WriteMessage(body []byte) error
   - ReadMessage must return the raw JSON body bytes; callers decode.
2. internal/transport/errors.go — sentinel errors: ErrMissingContentLength, ErrIncompleteHeader, ErrIncompleteBody, ErrHeaderTooLarge.
3. internal/transport/codec_test.go — table-driven tests covering:
   - round trip of 20 payloads from 1 byte to 1 MB
   - CRLF and LF header separators
   - malformed headers (missing Content-Length, negative length, non-integer length)
   - truncated body (EOF mid-body)
   - concurrent writers are serialized (WriteMessage is thread-safe via mutex)
4. Benchmarks in internal/transport/bench_test.go — measure throughput for 1 KB and 100 KB messages.

CONSTRAINTS:
- Pure standard library. No external deps.
- Header buffer cap: 64 KB (larger = ErrHeaderTooLarge).
- Writer: single Write call per message if possible (use bytes.Buffer → one w.Write).
- Zero allocations in the hot path where achievable (reuse buffers).
- Maximum body size: 128 MB.

Read the phase doc first, then implement.
```

### Agent 1B — JSON-RPC 2.0 client

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the JSON-RPC 2.0 client layer on top of the framed transport.
This layer handles request/response correlation by id and routes server-push
notifications to typed subscribers.

FIRST: Read docs/phase_go_01_protocol.md, specifically the "Agent 1B" section.

CONTEXT:
- Depends on internal/transport/ (from Agent 1A). Assume its API as specified in the phase doc even if 1A has not yet landed — use the interface.
- Depends on internal/protocol/ types (from Agent 1C) for message marshaling. Define a minimal json.RawMessage-based path that Agent 1C's types plug into.
- JSON-RPC 2.0 spec: requests have id + method + params; responses have id + result/error; notifications have method + params, no id.
- Concurrency model: one goroutine reads, one goroutine writes, callers register pending calls via a map keyed by id.

YOUR DELIVERABLES:
1. internal/rpc/client.go — exported Client type.
   - NewClient(r io.Reader, w io.Writer, logger *slog.Logger) *Client
   - (c *Client) Call(ctx context.Context, method string, params any, result any) error — blocks until response or ctx cancel
   - (c *Client) Notify(method string, params any) error — fire-and-forget (used for permissionRes etc.)
   - (c *Client) Subscribe(method string, handler func(params json.RawMessage)) (unsubscribe func())
   - (c *Client) Start() — launches reader goroutine
   - (c *Client) Close() error — stops reader, cancels all pending calls
2. internal/rpc/pending.go — internal correlation map (sync.Map or mutex+map).
3. internal/rpc/ids.go — atomic monotonic id generator (int64).
4. internal/rpc/client_test.go — unit tests with in-memory pipes:
   - successful Call round trip
   - error response mapping to Go error type
   - context cancellation aborts pending Call
   - multiple concurrent Calls with out-of-order responses
   - notifications routed to subscribers
   - subscribe/unsubscribe lifecycle
5. Error taxonomy: CallError{Code int; Message string; Data json.RawMessage} implementing error.

CONSTRAINTS:
- Do NOT parse params/result deeply here — use json.RawMessage and let callers decode via their own types.
- Reader goroutine must never panic on malformed input; log and continue.
- On transport-level errors (pipe broken, EOF), fail all pending calls and close subscriber channels.
- Default call timeout: 60s (caller overrides via ctx).

Read the phase doc first, then implement.
```

### Agent 1C — Protocol types

```
[AGENT PROMPT — copy/paste to your coding agent]

You are writing Go structs for every JSON-RPC message the poor-cli server exposes.
These types are the contract for all higher layers; getting the field names,
JSON tags, and optionality right is critical.

FIRST: Read docs/phase_go_01_protocol.md in full — it contains a complete method
catalog with exact params/result schemas for every method the client will use.

CONTEXT:
- Reference: /Users/gongahkia/Desktop/coding/projects/poor-cli/poor_cli/server/handlers/ — every .py file there is a handler with typed params and response.
- Key handlers: chat.py, chat_streaming.py, providers.py, diff_review.py, timeline.py, cost.py, sessions.py, mcp.py.
- JSON field naming: camelCase in wire protocol (e.g. `requestId`, `contextFiles`, `apiKey`). Use `json:"requestId"` tags.
- Optional fields use pointer types or `omitempty`.

YOUR DELIVERABLES:
1. internal/protocol/init.go — InitializeParams, InitializeResult, Capabilities, SecurityCaps, RepoIndexStats.
2. internal/protocol/chat.go — ChatParams, ChatResult (accumulated text), ChatStreamingParams.
3. internal/protocol/notifications.go — notification param types:
   - StreamChunk {RequestID, Chunk, Done, Reason}
   - ThinkingChunk {RequestID, Chunk}
   - ToolEvent {RequestID, EventType, ToolName, ToolArgs, ToolResult, CallID, Diff, Paths, CheckpointID, Changed, Message, OutputFilter, OriginalSize, FilteredSize}
   - CostUpdate {RequestID, InputTokens, OutputTokens, EstimatedCost, ModelName, CacheReadTokens, CacheWriteTokens}
   - Progress {RequestID, Phase, Message, IterationIndex, IterationCap}
   - PermissionReq {RequestID, RequestKey, ToolName, Description, Details, Rationale}
   - PermissionRes {RequestID, RequestKey, Decision, RememberScope}
   - ToolChunk (method "tool.chunk") {EventID, TurnID, ToolCallID, ToolName, Chunk}
   - InlineChunk {RequestID, Chunk, Done}
4. internal/protocol/cancel.go — CancelParams, CancelResult.
5. internal/protocol/providers.go — ProviderInfo, SwitchProviderParams, ListProvidersResult (map[string]ProviderDetail), ProviderDetail, ModelTierDetail, SetApiKeyParams.
6. internal/protocol/diff.go — DiffListParams, DiffPreview, DiffStageParams, AcceptParams, RejectParams, RegenParams, HunkDetail.
7. internal/protocol/timeline.go — TimelineEvent, TimelineListParams, CancelEventParams, RetryEventParams.
8. internal/protocol/cost.go — CostSnapshot, CostSummary, ContextPressure, ContextBreakdown, SavingsSnapshot.
9. internal/protocol/sessions.go — SessionSummary, ListSessionsResult, SwitchSessionParams, Checkpoint, ListCheckpointsResult.
10. internal/protocol/mcp.go — McpServer, McpListResult, McpToggleParams, McpHealth, McpTestParams.
11. internal/protocol/methods.go — const strings for every method name. Example:
    ```go
    const (
        MethodInitialize          = "initialize"
        MethodChatStreaming       = "poor-cli/chatStreaming"
        MethodStreamChunk         = "poor-cli/streamChunk"
        // ...
    )
    ```
12. internal/protocol/protocol_test.go — marshal/unmarshal round-trip tests for every struct using real example payloads captured from Python handlers.

CONSTRAINTS:
- Do NOT invent fields. If a field is uncertain, read the Python handler and the Lua rpc.lua usage.
- Use pointer types for truly optional fields where "absent" differs from "zero value".
- Match camelCase on the wire. Go struct field is PascalCase.
- For notifications with many optional fields (ToolEvent), use `omitempty` on the serializer side but not the deserializer.
- Do NOT add methods to these types beyond marshaling helpers.
- Do not use a code generator; hand-write the structs for full control and minimal deps.

Read the phase doc first, then implement.
```

### Agent 1D — Server process lifecycle

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the child process manager that spawns poor-cli-server,
wires its stdin/stdout to the RPC client, monitors its health, and shuts it
down cleanly on exit.

FIRST: Read docs/phase_go_01_protocol.md, specifically the "Agent 1D" and
"Server lifecycle" sections.

CONTEXT:
- The server command: `poor-cli-server --stdio`. If POOR_CLI_SERVER_PATH env is set, use that path instead. Otherwise resolve via exec.LookPath.
- Stderr carries server logs — capture to a ring buffer + optional file.
- Optional env vars the client can pass through: POOR_CLI_SERVER_LOG_FILE, POOR_CLI_TURN_USERNAME, POOR_CLI_TURN_CREDENTIAL.
- The server writes a session-id to stderr on startup but clients usually ignore it; default session is resolved inside the server.

YOUR DELIVERABLES:
1. internal/server/manager.go — Manager struct managing the os/exec.Cmd + pipes.
   - NewManager(cfg Config) *Manager
   - (m *Manager) Start(ctx context.Context) error — starts child, returns when process is ready for the first initialize call (detect by reading first stderr line or a small timeout).
   - (m *Manager) Stdin() io.Writer
   - (m *Manager) Stdout() io.Reader
   - (m *Manager) Wait() error — blocks until exit
   - (m *Manager) Shutdown(ctx context.Context) error — sends sigterm, waits 3s, then sigkill
   - (m *Manager) TailStderr(n int) []string — return last n log lines
2. internal/server/discovery.go — resolve the server binary path with this precedence: POOR_CLI_SERVER_PATH env > exec.LookPath("poor-cli-server") > exec.LookPath("poor-cli") (legacy) > error.
3. internal/server/manager_test.go — use a fake server binary (script) that echoes init/chat to verify:
   - manager detects server missing with helpful error
   - Shutdown escalates to SIGKILL after timeout
   - stderr is captured to ring buffer
   - restart semantics (Manager.Restart if implemented)
4. internal/server/health.go — optional health probe: periodic no-op method call; flag process as unhealthy if call fails 3 times consecutively.

CONSTRAINTS:
- Do NOT block the main goroutine — all I/O goroutines must be cleanly stoppable.
- stderr must be read continuously or the pipe will block.
- On Windows, use CreateProcess with CREATE_NEW_PROCESS_GROUP to allow clean signaling; behind build tag.
- Pre-ready detection: stderr log parse + 500ms grace; readiness is proven by `initialize` returning successfully (Wave 5 responsibility).

Read the phase doc first, then implement.
```

---

## Wave 2 — TUI Foundation

**Agents: 4 (all parallel)**
**Reference document:** `docs/phase_go_02_tui_foundation.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W0

Intra-wave collisions: **none**. Each agent owns a disjoint package directory.

### Agent 2A — Bubbletea app shell

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the Bubbletea root model and main loop for the TUI. This
is the frame that widgets slot into. No chat logic, no RPC — pure layout + routing.

FIRST: Read docs/phase_go_02_tui_foundation.md, specifically the "Agent 2A" section
for the screen region map and messaging contract.

CONTEXT:
- Bubbletea follows The Elm Architecture. Keep update/view deterministic and side-effect free.
- Layout: top bar (1 row) + main area (chat view, scrolls) + input area (3–10 rows, autosizes) + status bar (1 row). Modal overlay region for palette/mention.
- Resize behaviour: preserve scroll anchor in chat; recompute input width.
- Mouse + bracketed paste: enabled from start.

YOUR DELIVERABLES:
1. internal/tui/app.go — root Model struct, Init/Update/View methods.
2. internal/tui/messages.go — app-level message types (custom tea.Msg): Resize, SwitchFocus, OpenModal, CloseModal, Toast, FocusTarget.
3. internal/tui/focus.go — focus router enumerating Input, Chat, Modal states with keybind ownership per focus.
4. internal/tui/regions.go — rectangle computation from terminal (w,h) → {topbar, chat, input, statusbar, modal}.
5. internal/tui/modal.go — modal stack (palette, mention, provider picker, permission prompt) with cover-style rendering.
6. internal/tui/app_test.go — model snapshot tests using teatest from github.com/charmbracelet/x/exp/teatest.

CONSTRAINTS:
- Keep app.go <400 LOC. Push widget logic into internal/tui/widgets/ (Wave 3 owns those files).
- Use tea.WithAltScreen() and tea.WithMouseCellMotion() by default.
- Do NOT import internal/rpc or internal/server directly — those come in via state (Agent 2D) and flows (Wave 5). The app model holds a state.AppState pointer only.
- Splash screen is included (see phase_go_02 Agent 2A IntroModel spec).

Read the phase doc first, then implement.
```

### Agent 2B — Theme & styles

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the lipgloss-based theming system. Every rendered region uses
named style tokens; no raw colors anywhere outside this package.

FIRST: Read docs/phase_go_02_tui_foundation.md, specifically the "Agent 2B"
section for the full style token list and theme-switching protocol.

CONTEXT:
- Target visual: Codex CLI / ADA / Clockwork aesthetic — subtle borders, high contrast text, role-colored chat bubbles (user=cyan, assistant=grey, tool=amber, system=dim).
- Two default themes: "dark" (true color on dark bg) and "light". User can define custom themes via YAML (see Agent 2C).
- Terminal capability detection: fall back to 256-color if truecolor not supported, monochrome if needed.

YOUR DELIVERABLES:
1. internal/theme/theme.go — Theme struct containing all style tokens as lipgloss.Style fields.
   Token names (at minimum): Base, Muted, Border, Focus, Error, Success, Warning, Info,
   ChatUser, ChatAssistant, ChatTool, ChatSystem, ChatCode, ChatLink, StatusBar, StatusBarActive,
   TopBar, InputField, InputFieldFocused, Modal, ModalTitle, Palette, PaletteHighlight,
   MentionList, MentionHighlight, CostGood, CostWarn, CostBad, ToolPending, ToolSuccess, ToolError.
2. internal/theme/dark.go, internal/theme/light.go — the two defaults.
3. internal/theme/loader.go — LoadFromYAML([]byte) (Theme, error); merges over dark defaults so user themes can be partial.
4. internal/theme/caps.go — terminal capability detection via env TERM, COLORTERM, NO_COLOR.
5. internal/theme/theme_test.go — snapshot tests rendering each token to a string; diff detection.

CONSTRAINTS:
- Zero colors hardcoded outside this package. Grep rule for reviewers: no `lipgloss.Color(` outside internal/theme/.
- Respect NO_COLOR env var (https://no-color.org): force monochrome.
- Palette: ADA-minimal dark default. Accent color #89b4fa (cool blue), muted #585858, warning #f9e2af, error #f38ba8. No chat-block backgrounds.

Read the phase doc first, then implement.
```

### Agent 2C — Config & keybindings

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the user configuration system: YAML config file, env-var
overrides, keybinding definitions, and the keybind → action dispatch table.

FIRST: Read docs/phase_go_02_tui_foundation.md, specifically the "Agent 2C"
section for the config schema and default keybindings.

CONTEXT:
- Config file path precedence: $XDG_CONFIG_HOME/gocli-poor/config.yaml > ~/.config/gocli-poor/config.yaml > $HOME/.gocli-poor.yaml.
- Env var prefix: GOCLI_POOR_*. Env overrides config.
- Keybindings follow the Bubbletea key.Binding pattern. Support chords (prefix + key).

YOUR DELIVERABLES:
1. internal/config/config.go — Config struct covering:
   - Theme (name or inline)
   - ServerPath (override POOR_CLI_SERVER_PATH)
   - DefaultProvider, DefaultModel
   - ContextBudgetTokens, MaxResponseTokens
   - AutoAcceptSafeEdits bool
   - HistoryFile string
   - LogLevel (debug/info/warn/error)
   - Keybindings map[string]string  # action → keybind string
2. internal/config/load.go — Load() (*Config, error): resolves precedence, merges defaults.
3. internal/config/defaults.go — ship defaults, including a canonical keybinding set:
   - submit = ctrl+enter
   - cancel = ctrl+c (while streaming) / esc (otherwise)
   - palette = /
   - mention = @
   - focus.chat = ctrl+j
   - focus.input = ctrl+i
   - scroll.up, scroll.down, scroll.top, scroll.bottom
   - accept.edit, reject.edit, regen.edit
   - quit = ctrl+q
4. internal/config/keys.go — Keymap struct with named key.Binding fields + action resolver.
5. internal/config/config_test.go — precedence tests, schema validation, malformed YAML.

CONSTRAINTS:
- Backwards-compat: adding config fields must never break older config files; always default missing fields.
- Do NOT couple to Bubbletea directly in config.go — keybindings produced as strings; internal/config/keys.go compiles them to key.Binding.
- Submit keybind is `Ctrl+Enter`; `Enter` inserts a newline.

Read the phase doc first, then implement.
```

### Agent 2D — App state store

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the central app state container. This is the single source
of truth for conversation history, current session, current provider, cost
totals, connection status, and in-flight request.

FIRST: Read docs/phase_go_02_tui_foundation.md, specifically the "Agent 2D"
section for the state schema and mutation protocol.

CONTEXT:
- State is mutated only through dispatched actions (Redux-style). The TUI root
  receives state via a pointer + subscribes to change events.
- Concurrency: mutations happen from multiple goroutines (RPC notifications,
  user input). Use a single goroutine that owns the state + channel of actions.

YOUR DELIVERABLES:
1. internal/state/store.go — Store struct:
   - NewStore() *Store
   - (s *Store) Snapshot() AppState — read-only copy
   - (s *Store) Dispatch(action Action)
   - (s *Store) Subscribe() (<-chan AppState, func())
2. internal/state/types.go — AppState struct containing:
   - Messages []Message (role, content, streaming, requestID, segments)
   - InFlight *InFlightRequest (requestID, startedAt, cancelFn)
   - Provider ProviderState (name, model, caps)
   - Cost CostState (session totals, last update)
   - Session SessionState (id, turns, checkpoints)
   - Connection ConnState (state enum: Disconnected, Starting, Ready, Error; lastError)
   - ContextPressure (tokens, budget, pct)
   - Toast queue []ToastItem
3. internal/state/actions.go — Action sum type (interface + concrete structs):
   ActionAppendMessage, ActionAppendChunk, ActionStartStream, ActionEndStream,
   ActionSetProvider, ActionUpdateCost, ActionSetConnection, ActionToast,
   ActionReplaceMessages, ActionUpdateContextPressure.
4. internal/state/reducer.go — pure reducers per action type, return new AppState.
5. internal/state/store_test.go — test concurrent dispatch correctness, subscriber fan-out, snapshot isolation.

CONSTRAINTS:
- AppState is immutable from outside the store. Return copies from Snapshot().
- Reducers must be pure — no I/O, no goroutines, no time.Now() (pass time via action payload).
- Max messages kept in memory before windowing: 1000.

Read the phase doc first, then implement.
```

---

## Wave 3 — Widgets

**Agents: 5 (all parallel)**
**Reference document:** `docs/phase_go_03_widgets.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W2

Intra-wave collisions: **none**. Each widget is a separate file and exported type.

### Agent 3A — Chat view

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the scrollable chat transcript widget — the centerpiece of the UI.
It renders a growing list of messages (user, assistant, tool) with markdown rendering
for assistant content and must support live streaming updates.

FIRST: Read docs/phase_go_03_widgets.md, specifically the "Agent 3A" section
for the widget interface contract and rendering rules.

CONTEXT:
- Depends on internal/markdown/ (Wave 4) for rendering streamed assistant text.
  If W4 hasn't landed, import a stub interface (markdown.Renderer) and mock it.
- Depends on internal/state/ (Wave 2D) for message data.
- Depends on internal/theme/ (Wave 2B) for styles.
- Visual model: each message is a "block" with an optional role label + body + metadata row (tool name, token count). Tool events render as collapsible/expandable panels.

YOUR DELIVERABLES:
1. internal/tui/widgets/chat.go — ChatView type:
   - New(theme *theme.Theme, mdRenderer markdown.Renderer) *ChatView
   - (c *ChatView) Update(msg tea.Msg) (*ChatView, tea.Cmd)
   - (c *ChatView) View(width, height int) string
   - (c *ChatView) SetMessages(msgs []state.Message)
   - (c *ChatView) AppendChunk(requestID string, chunk string) — streaming append to last message
   - (c *ChatView) ScrollUp(n int), ScrollDown(n int), ScrollToBottom(), ScrollToTop()
   - (c *ChatView) IsAtBottom() bool
2. internal/tui/widgets/message.go — Message rendering per role.
3. internal/tui/widgets/tool_block.go — collapsible tool-call rendering (header: tool name + status; expandable: args + output).
4. internal/tui/widgets/chat_test.go — snapshot tests:
   - streaming paint (append does not flicker full widget)
   - scroll anchor preserved on resize
   - autoscroll on append when at bottom; stays in place when user scrolled up
   - long messages wrap correctly with runewidth

CONSTRAINTS:
- Diff-based repaint: only the tail of the in-flight message re-renders each frame. Do NOT rebuild the whole string.
- Cap render cadence to 60 Hz via internal ticker.
- Mouse wheel support: MouseMsg with WheelUp/WheelDown.
- Role label rendering: inline prefix ("you" / "poor-cli") in muted text at start of each message. No boxes, no background color.

Read the phase doc first, then implement.
```

### Agent 3B — Input editor

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the multi-line input editor: cursor, wrapping, paste, history
cycling, and hooks for slash commands and @mentions.

FIRST: Read docs/phase_go_03_widgets.md, specifically the "Agent 3B" section.

CONTEXT:
- Depends on internal/theme (for border+focus styles) and internal/config (for keybindings).
- The input opens the palette (3D) when first char is "/" and mention picker (3E) when typing "@". Those widgets are separate — this widget emits OpenModal messages and receives inserts back.
- History: up arrow cycles through previous user messages. Down arrow un-cycles.

YOUR DELIVERABLES:
1. internal/tui/widgets/input.go — InputField type:
   - New(theme *theme.Theme, km *config.Keymap) *InputField
   - Update/View/Focus/Blur standard pattern
   - (i *InputField) Value() string, SetValue(string), Clear(), InsertAt(string), CursorPos() int
   - Emits SubmitMsg{Text} on submit key, CancelMsg on cancel key, PaletteOpenMsg, MentionOpenMsg when triggers match.
2. internal/tui/widgets/history.go — ring buffer with up/down cursor; persists to state.HistoryFile on submit.
3. internal/tui/widgets/input_test.go — keypress sequences for: typing, newline, backspace, ctrl+enter submit, ctrl+c cancel, paste (bracketed-paste sequence).

CONSTRAINTS:
- Properly handle Unicode with go-runewidth (emoji, CJK, ZWJ sequences).
- Submit triggers only on ctrl+enter to avoid accidental sends on plain enter.
- Bracketed paste must not interpret the pasted text's newlines as submits.
- Submit = `Ctrl+Enter`; `Enter` = newline.

Read the phase doc first, then implement.
```

### Agent 3C — Status bar / HUD

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the bottom status bar: provider/model, session, context pressure,
token/cost counters, connection indicator. Think tmux status-line density.

FIRST: Read docs/phase_go_03_widgets.md, specifically the "Agent 3C" section.

CONTEXT:
- Depends on internal/state for subscriptions.
- Slot layout (left → right): [ConnDot] [Provider:Model] [Session#] [CtxPct] [Tokens in/out] [$cost] — space allowing. Truncate rightmost slots first.

YOUR DELIVERABLES:
1. internal/tui/widgets/statusbar.go — StatusBar type with slot renderer.
2. internal/tui/widgets/topbar.go — TopBar type showing title + breadcrumb (cwd + branch if git).
3. internal/tui/widgets/statusbar_test.go — truncation tests at various widths.

CONSTRAINTS:
- Reads state via subscription; does not hold its own mutable state beyond cached snapshot.
- Ignore ANSI width correctly in truncation (use lipgloss.Width).
- Always visible slots: provider:model and cost. Everything else is truncatable.

Read the phase doc first, then implement.
```

### Agent 3D — Command palette (slash commands)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the slash-command palette: triggered by "/" as the first char of
input, it shows a filterable list of commands (built-in + server-provided custom
commands) with fuzzy matching.

FIRST: Read docs/phase_go_03_widgets.md, specifically the "Agent 3D" section
for the command registry interface.

CONTEXT:
- Built-in commands: /compact, /clear, /provider, /model, /session, /cost, /diff, /watch, /quit, /help.
- Server-side custom commands: loaded via poor-cli/listCustomCommands and poor-cli/getCommandManifest.
- Fuzzy matching: use github.com/sahilm/fuzzy.

YOUR DELIVERABLES:
1. internal/tui/widgets/palette.go — Palette type:
   - New(theme, registry *commands.Registry) *Palette
   - Emits SelectCommandMsg{CommandID, Args} on enter.
2. internal/tui/widgets/commands_registry.go — Command struct {ID, Label, Description, Usage, Origin (builtin/custom)}.
3. internal/tui/widgets/palette_test.go — filtering, selection, escape-to-close.

CONSTRAINTS:
- Palette does NOT execute commands — it emits a message. Execution is Wave 5 flows.
- Command list refreshes when server sends providerChanged events; the palette re-fetches.
- No org-specific built-in commands beyond the standard set.

Read the phase doc first, then implement.
```

### Agent 3E — Mention picker (@file)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the file-mention picker: triggered by "@" in input, it shows a
fuzzy-matched list of repo files. On select, the file path is inserted into the
input and also appended to the chat request's contextFiles list.

FIRST: Read docs/phase_go_03_widgets.md, specifically the "Agent 3E" section.

CONTEXT:
- File list sourced from internal/state; state hydrates it via `poor-cli/repoMap` or `poor-cli/contextStatus` on startup and periodically on file changes.
- Fuzzy matching with sahilm/fuzzy. Weight: path contains term > basename contains term.

YOUR DELIVERABLES:
1. internal/tui/widgets/mention.go — MentionPicker type, emits SelectMentionMsg{Path}.
2. internal/tui/widgets/mention_test.go — matching order, disambiguation when two files share basename.

CONSTRAINTS:
- Lazy-load the file list — first open triggers fetch from state; subsequent opens reuse.
- Preview: show first 5 lines of selected file on the right half of the picker.
- Max visible rows in picker: 10.

Read the phase doc first, then implement.
```

---

## Wave 4 — Streaming Markdown Tokenizer

**Agents: 4 (4A ∥ 4B ∥ 4D parallel; 4C waits on 4A + 4B)**
**Reference document:** `docs/phase_go_04_streaming_markdown.md`
**Estimated time per agent:** 1–3 days
**Prerequisites:** W0

This wave is the project's technical centerpiece. It exists because Glamour re-renders full buffers on each delta → visible flicker at streaming rates. We replace it with an incremental event-emitting parser.

### Agent 4A — Block tokenizer

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the block-level incremental tokenizer for markdown. It
consumes byte chunks and emits block events (BlockOpen / BlockClose / RawLine)
only when decisions are unambiguous.

FIRST: Read docs/phase_go_04_streaming_markdown.md — the full design doc. The
"Agent 4A" section specifies exact decision rules per block type.

CONTEXT:
- This is a CommonMark-subset, streaming-friendly parser — not full CommonMark.
- Supported blocks: Paragraph, Heading1..6 (ATX: "# "), CodeFence ("```info"), Blockquote ("> "), List (unordered -/+/*; ordered digit+.), ThematicBreak (---/***/___).
- Out of scope: setext headings, HTML blocks, link reference definitions, tables (handled later if at all).
- "Commit" rule: a block is committable when the next line is known to be outside it (blank line for paragraph, closing fence for code, indent decrease for list). Between commits, events may be "tentative" and can be rewritten.

YOUR DELIVERABLES:
1. internal/markdown/block.go — BlockTokenizer type:
   - NewBlockTokenizer() *BlockTokenizer
   - (b *BlockTokenizer) Write(chunk []byte)
   - (b *BlockTokenizer) Drain() []Event
   - (b *BlockTokenizer) Close() []Event
2. internal/markdown/events.go — Event interface + concrete types:
   BlockOpenEvent {Kind BlockKind, Info string, Line int}
   BlockCloseEvent {Kind BlockKind, Line int}
   RawLineEvent {Kind BlockKind, Text string, Line int}  // carries raw bytes for inline tokenizer
   CommitEvent {UpToLine int}
3. internal/markdown/block_test.go — scenario suite covering every block type:
   - paragraph with trailing inline content
   - code fence with language info string
   - heading variants #..######
   - list item reflow
   - chunk boundary at every single position for a 2 KB sample document (fuzz-like)

CONSTRAINTS:
- O(n) in total bytes seen. No backtracking past 256-byte lookahead.
- Write must be safe to call with arbitrary chunk sizes (including single bytes).
- Drain returns only "safe" events — ones that cannot be retroactively invalidated.
- Never emit duplicate events.
- Idempotent Close — can be called multiple times; first returns pending events, subsequent returns nil.
- Setext headings: NOT supported (they require unbounded lookahead).

Read the phase doc first, then implement.
```

### Agent 4B — Inline tokenizer

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the inline tokenizer: takes block-text content (paragraph,
heading, list item) and emits inline events for emphasis, strong, code spans,
and links. Streaming-aware: holds back bytes until context is disambiguous.

FIRST: Read docs/phase_go_04_streaming_markdown.md, specifically the "Agent 4B"
section for flanking rules and holdback protocol.

CONTEXT:
- Inputs are RawLineEvent bodies from the block tokenizer (Agent 4A).
- Supported inline: emphasis (*..*, _.._), strong (**..**, __..__), code span (`..`), link ([text](url)), autolink (<url>).
- Not supported: images, inline HTML, hard line breaks (keep as whitespace).
- Holdback rule: if a potential inline open has been seen but not matched, buffer up to 128 bytes. If buffer fills or block ends, flush as literal text.

YOUR DELIVERABLES:
1. internal/markdown/inline.go — InlineTokenizer type:
   - NewInlineTokenizer() *InlineTokenizer
   - (i *InlineTokenizer) FeedLine(rawLine RawLineEvent) []Event
   - (i *InlineTokenizer) Close() []Event
2. Events added to internal/markdown/events.go:
   InlineOpenEvent {Kind InlineKind}
   InlineCloseEvent {Kind InlineKind}
   TextEvent {Value string}
   LinkEvent {Text, URL string}
3. internal/markdown/inline_test.go — cases including:
   - "*foo* *bar*" emphasis
   - "**foo** vs *foo* vs ***foo***" ambiguity
   - "`code` backtick"
   - "[text](url)" link
   - degraded "*foo bar" flush as literal on line end
   - CommonMark flanking edge cases (at least 20 canonical examples)

CONSTRAINTS:
- Nested emphasis is supported but nested code spans are not (CommonMark rule).
- Line-level — inline tokenizer processes one line at a time; inter-line continuation handled by the block layer.
- Autolinks are supported only in the strict `<url>` form. Bare URL detection in plain text is out of scope.

Read the phase doc first, then implement.
```

### Agent 4C — Stream renderer

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building the renderer that consumes block+inline events and produces
themed terminal output with diff-based paint support. This is the layer the
chat view (Agent 3A) actually calls.

FIRST: Read docs/phase_go_04_streaming_markdown.md, specifically the "Agent 4C"
section — this doc contains the full API contract and the segment model.

CONTEXT:
- Depends on internal/markdown/block.go (Agent 4A), internal/markdown/inline.go (Agent 4B), internal/markdown/highlight.go (Agent 4D for code-fence highlighting), internal/theme (for styles).
- Must support "render tail since commit N" so the chat widget can repaint only the growing edge of a streaming message — not the whole message.

YOUR DELIVERABLES:
1. internal/markdown/renderer.go — Renderer type:
   - NewRenderer(theme *theme.Theme, highlighter *Highlighter, width int) *Renderer
   - (r *Renderer) Feed(events []Event)
   - (r *Renderer) Full() string  // full rendered buffer
   - (r *Renderer) TailSince(mark Mark) (tail string, mark Mark)
   - (r *Renderer) Resize(width int)  // re-wrap
2. internal/markdown/stream.go — Streamer type that owns both block+inline tokenizers and a renderer, exposed as a single Parser:
   - NewStreamer(theme, highlighter, width int) *Streamer
   - (s *Streamer) Write(chunk []byte)  // feeds bytes
   - (s *Streamer) Drain() (events []Event, rendered string)
   - (s *Streamer) Mark() Mark  // for chat widget's tail tracking
3. internal/markdown/renderer_test.go — golden output tests for each block type; ANSI escape-aware snapshot comparator.
4. internal/markdown/stream_test.go — feeds a 4KB markdown document byte-by-byte and asserts:
   - final Full() matches full-document render
   - TailSince(prev) at each tick only grows (monotonic)
   - no ANSI escape is ever split across paints (flicker guarantee)

CONSTRAINTS:
- MUST NOT depend on github.com/charmbracelet/glamour. That is the thing we're replacing.
- Code fence lines re-highlight on each delta for the in-progress line only. Completed lines are frozen.
- Wrapping respects runewidth for CJK/emoji.
- Render must be pure-function from (events, theme, width) — no time or globals.
- Cap internal segment count to avoid pathological inputs (split once per 4096 chars).
- Maximum wrap width: terminal width − 2 columns (reserved for future border).

Read the phase doc first, then implement.
```

### Agent 4D — Chroma integration (syntax highlighting)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are wrapping chroma as a per-language highlighter that the markdown renderer
calls for code-fence contents. Must support "highlight current line only"
incremental mode for streamed code blocks.

FIRST: Read docs/phase_go_04_streaming_markdown.md, specifically the "Agent 4D"
section.

CONTEXT:
- chroma v2 API: chroma.Lexers.Get("go"), lexer.Tokenise(nil, input) → Iterator.
- For streaming: re-highlight the in-progress line on each delta; completed lines cached.

YOUR DELIVERABLES:
1. internal/markdown/highlight.go — Highlighter type:
   - NewHighlighter(theme *theme.Theme) *Highlighter
   - (h *Highlighter) HighlightLine(lang, line string) string  // returns lipgloss-styled string
   - (h *Highlighter) HighlightBlock(lang, code string) string  // for committed blocks
   - Detect language fallback: if lang is unknown, use "fallback" analyser.
2. internal/markdown/highlight_test.go — golden output for Go, Python, JSON, bash.

CONSTRAINTS:
- Fallback to plain text if chroma does not have the language — never error.
- Cache lexer lookup per-lang (chroma lexer resolution is cheap but not free).
- Chroma style: `monokai` for dark theme; `friendly` for light theme.

Read the phase doc first, then implement.
```

---

## Wave 5 — Flows

**Agents: 5 (4 parallel + 1 serial — see collision note)**
**Reference document:** `docs/phase_go_05_flows.md`
**Estimated time per agent:** 2–3 days
**Prerequisites:** W1 + W3 + W4

### Intra-wave collisions

- **`internal/tui/app.go`** is shared by **5A** (wires chat flow into app update loop) and **5E** (wires HUD updates). Both need to extend the main Model's Update method.

### Proposed sub-waves

- **Sub-wave α (parallel):** 5B, 5C, 5D — each owns its own flow package and does not touch app.go.
- **Sub-wave β (serial):** 5A lands first (establishes how flows hook into app.go via a FlowRegistry pattern). 5E then plugs in using the registry, no line collision.

### Agent 5A — Chat send/stream flow

```
[AGENT PROMPT — copy/paste to your coding agent]

You are wiring the end-to-end chat flow: user presses submit → RPC call to
poor-cli/chatStreaming → stream notifications → state updates → chat view repaints.
This is the "does it work" moment of the project.

FIRST: Read docs/phase_go_05_flows.md, specifically the "Agent 5A" section and
the shared FlowRegistry pattern.

CONTEXT:
- Depends on internal/rpc (Wave 1B), internal/protocol (Wave 1C), internal/state (Wave 2D), internal/tui/widgets/chat (Wave 3A), internal/markdown (Wave 4).
- Reference: nvim-poor-cli/lua/poor-cli/chat.lua shows the full Lua-side flow; mirror it in Go.

YOUR DELIVERABLES:
1. internal/tui/flows/registry.go — FlowRegistry pattern so later flows register into app.go without editing it.
2. internal/tui/flows/chat.go — ChatFlow type:
   - Start(text string, ctxFiles []string) — builds ChatStreamingParams, launches Call in a goroutine, returns immediately.
   - Subscribes to "poor-cli/streamChunk", "poor-cli/thinkingChunk", "poor-cli/toolEvent", "poor-cli/costUpdate", "poor-cli/progress" — routes each to state dispatch actions.
   - Cancel(requestID string) — calls poor-cli/cancelRequest.
3. internal/tui/flows/chat_test.go — integration test with a mock RPC client replaying a recorded streaming session.

CONSTRAINTS:
- Every notification must be routed even if the chat view is not focused (state updates continue).
- On RPC error (server crash mid-stream), reset in-flight state and surface a Toast.
- Auto-scroll during streaming: YES when the user is at the bottom; detaches when the user scrolls up.

Read the phase doc first, then implement.
```

### Agent 5B — Slash command handlers

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the runtime for slash commands: map SelectCommandMsg
from the palette (Agent 3D) to concrete actions, including server RPC calls
for server-backed commands.

FIRST: Read docs/phase_go_05_flows.md, specifically the "Agent 5B" section and
the command manifest.

CONTEXT:
- Client-side commands: /clear (state reset), /quit, /help (modal).
- Server-backed commands: /compact (poor-cli/clearHistory + summary), /provider (switchProvider), /model (switchProvider with model arg), /session (switchSession), /cost (poor-cli/getSessionCost), /diff (open diff review), /watch (toggle watch panel).
- Custom commands: fetched via poor-cli/listCustomCommands.

YOUR DELIVERABLES:
1. internal/tui/flows/commands.go — CommandDispatcher + one function per command.
2. internal/tui/flows/commands_test.go — ensure each command routes correctly; mock RPC for server-backed ones.

CONSTRAINTS:
- Do NOT import internal/rpc directly — go through a typed interface injected at construction to keep tests simple.
- No org-specific custom commands beyond the standard set.

Read the phase doc first, then implement.
```

### Agent 5C — Providers, models, sessions

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing the provider/model/session pickers — modal widgets backed
by server RPC calls.

FIRST: Read docs/phase_go_05_flows.md, specifically the "Agent 5C" section.

CONTEXT:
- Relevant RPC: poor-cli/listProviders, poor-cli/switchProvider, poor-cli/listSessions, poor-cli/switchSession, poor-cli/listCheckpoints, poor-cli/restoreSession.
- Uses the modal stack from Agent 2A.

YOUR DELIVERABLES:
1. internal/tui/flows/providers.go — ProviderPicker modal + dispatch.
2. internal/tui/flows/sessions.go — SessionPicker modal + dispatch.
3. internal/tui/flows/api_key.go — APIKeyPrompt when server returns needsApiKey=true after initialize.
4. Tests for each.

CONSTRAINTS:
- API key entry: never log the key. Use a concealed input field.
- Keyring persistence: offered by default with the "save to keyring" checkbox pre-ticked.

Read the phase doc first, then implement.
```

### Agent 5D — Diff review + permissions

```
[AGENT PROMPT — copy/paste to your coding agent]

You are implementing two interactive flows: the diff review panel (accept / reject
/ regen hunks produced by the agent) and the permission prompt (when the agent
wants to run a risky tool).

FIRST: Read docs/phase_go_05_flows.md, specifically the "Agent 5D" section.

CONTEXT:
- Diff RPC: poor-cli/listPendingEdits, poor-cli/previewEdit, poor-cli/acceptHunk, poor-cli/rejectHunk, poor-cli/regenerateHunk, poor-cli/acceptAll, poor-cli/rejectAll.
- Permission flow: server sends poor-cli/permissionReq notification mid-stream; we show a modal; on decision, we send poor-cli/permissionRes notification.

YOUR DELIVERABLES:
1. internal/tui/flows/diff.go — DiffReviewFlow + modal widget rendering a unified diff with hunk-level actions.
2. internal/tui/flows/permissions.go — PermissionFlow + modal.
3. Tests including fixture-based diff rendering with ANSI checks.

CONSTRAINTS:
- Diff view must handle large hunks (lazy render + scroll).
- Permission decision must be delivered within the server's timeout (default 30s) or the server auto-denies.
- Auto-accept "safe" edits is enabled by default (`config.AutoAcceptSafeEdits = true`).

Read the phase doc first, then implement.
```

### Agent 5E — Cost & context HUD updates

```
[AGENT PROMPT — copy/paste to your coding agent]

You are wiring cost and context-pressure updates from server notifications into
the status bar (Agent 3C). Also implements the /cost modal showing the detailed
dashboard.

FIRST: Read docs/phase_go_05_flows.md, specifically the "Agent 5E" section.

CONTEXT:
- Depends on 5A (FlowRegistry) — MUST land after 5A.
- Relevant RPC/notifications: poor-cli/costUpdate (streaming), poor-cli/getSessionCost, poor-cli/getContextPressure, poor-cli/getEconomySavings.

YOUR DELIVERABLES:
1. internal/tui/flows/hud.go — HudFlow subscribes to cost notifications, dispatches state actions.
2. internal/tui/flows/cost_modal.go — /cost slash command → modal with provider breakdown + savings.
3. Tests.

CONSTRAINTS:
- Throttle HUD updates to 10 Hz — cost notifications fire per chunk, TUI doesn't need that.
- Cost-per-completion thresholds: $0.05 warns yellow; $0.25 warns red.

Read the phase doc first, then implement.
```

---

## Wave 6 — Polish & Ship

**Agents: 4 (all parallel)**
**Reference document:** `docs/phase_go_06_polish_ship.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W5

### Agent 6A — Test suite completion

```
[AGENT PROMPT — copy/paste to your coding agent]

You are expanding the test suite to 80%+ coverage across internal/* and adding
one end-to-end test that spawns a real poor-cli-server, drives a chat turn,
and asserts the full rendered output.

FIRST: Read docs/phase_go_06_polish_ship.md, specifically the "Agent 6A" section.

CONTEXT:
- Existing tests: each wave's agent left per-package tests. This wave adds cross-cutting tests.
- Real server binary required at $GOCLI_POOR_E2E_SERVER for e2e; skip with `testing.Short()` otherwise.

YOUR DELIVERABLES:
1. test/e2e/chat_test.go — full TUI → server → response → render.
2. test/fixtures/ — recorded streaming sessions for reproducible tests.
3. Makefile targets: test-unit, test-integration, test-e2e, coverage.
4. Coverage report in CI; badge in README.

CONSTRAINTS:
- E2E test max runtime 30s.
- E2E provider: `ollama` with a local model (keeps test cost at zero).

Read the phase doc first, then implement.
```

### Agent 6B — Distribution

```
[AGENT PROMPT — copy/paste to your coding agent]

You are finalising the goreleaser config, writing install scripts, and setting
up a Homebrew tap for single-command install.

FIRST: Read docs/phase_go_06_polish_ship.md, specifically the "Agent 6B" section.

YOUR DELIVERABLES:
1. .goreleaser.yml complete with darwin/linux/windows × amd64/arm64.
2. homebrew-tap/ directory (if standalone) or PR to existing tap.
3. install.sh — curl | bash installer for macOS/Linux.
4. GitHub Action for release on tag push.

CONSTRAINTS:
- Binary name: gocli-poor. Install target: /usr/local/bin/gocli-poor or $HOME/.local/bin/.
- Tap repo: `gongahkia/homebrew-tap`. Maintainer: gongahkia.

Read the phase doc first, then implement.
```

### Agent 6C — User documentation

```
[AGENT PROMPT — copy/paste to your coding agent]

You are writing the README, keybinding reference, config guide, and 5-minute
quickstart video script.

FIRST: Read docs/phase_go_06_polish_ship.md, specifically the "Agent 6C" section.

YOUR DELIVERABLES:
1. README.md — overview, install, 60-second demo, links to deeper docs.
2. docs/quickstart.md — 5-minute walkthrough.
3. docs/keybindings.md — full reference.
4. docs/config.md — every config field documented.
5. docs/troubleshooting.md — common issues.

CONSTRAINTS:
- No screenshots in repo (binary bloat); use asciicast links.
- Include an asciicast demo link in README; do NOT inline a GIF (binary bloat).

Read the phase doc first, then implement.
```

### Agent 6D — Benchmarks & performance

```
[AGENT PROMPT — copy/paste to your coding agent]

You are measuring and optimising the three performance-sensitive paths: render
latency per frame, streaming throughput, and startup time.

FIRST: Read docs/phase_go_06_polish_ship.md, specifically the "Agent 6D" section.

CONTEXT:
- Targets: 60 Hz render with zero dropped frames at 200 tok/s streaming rate; startup <200 ms to first paint; RSS <50 MB steady-state.

YOUR DELIVERABLES:
1. bench/render_test.go — markdown renderer benchmark.
2. bench/streaming_test.go — end-to-end streaming pipeline with synthetic server.
3. bench/startup_test.go — time.Now() → first paint.
4. Report in docs/benchmarks.md with before/after tables.

CONSTRAINTS:
- Use pprof-driven optimisation; do not micro-optimise without profiles.
- Performance targets in phase_go_06 apply as written (measured on M-series laptop).

Read the phase doc first, then implement.
```

---

## Wave 7 — Multiplayer Backend Robustness

**Agents: 4 (sub-wave α parallel 7B+7C+7D; sub-wave β 7A)**
**Reference document:** `docs/phase_go_07_multiplayer_backend.md`
**Estimated time per agent:** 2–4 days
**Prerequisites:** none (Python-only; runs in parallel with Go waves)

All four features gate behind `multiplayer.features.*` config flags defaulting off — existing deployments are byte-identical after the upgrade.

### Agent 7A — Multi-prompter parallel queue

```
[AGENT PROMPT — copy/paste to your coding agent]

You are extending the poor-cli Python backend so that multiple approved prompters
in the same multiplayer room can submit chat turns concurrently, with a
round-robin per-user queue and owner-authoritative serial dispatch.

FIRST: Read docs/phase_go_07_multiplayer_backend.md, specifically the "Agent 7A" section.

CONTEXT:
- Existing queue + dispatch lives in /Users/gongahkia/Desktop/coding/projects/poor-cli/poor_cli/multiplayer.py (lines 152–2048). Read the `_room_worker`, `_QUEUE_METHODS`, and `RoomState` structures first.
- Existing session/role logic is in poor_cli/multiplayer_session.py; extend `rebalance_room_roles` to allow multiple active prompters.
- Feature is gated behind config flag `multiplayer.features.multiPrompter` (default false). When off, behavior must be byte-identical to today.

YOUR DELIVERABLES:
1. poor_cli/multiplayer_queue.py — MultiPrompterQueue class with round-robin per-user FIFO, `max_per_user` cap, queue snapshot.
2. poor_cli/multiplayer.py — route chat methods into the new queue when flag is on; broadcast `poor-cli/queueUpdated` on every queue mutation.
3. poor_cli/multiplayer_session.py — rebalance_room_roles allows multiple prompters in multi-prompter mode.
4. poor_cli/server/handlers/multiplayer.py — register `poor-cli/listRoomQueue` and `poor-cli/cancelQueueItem` handlers.
5. tests/test_multiplayer_queue.py — round-robin, starvation prevention, disconnect cleanup, feature flag regression.

CONSTRAINTS:
- Feature flag off → byte-identical legacy behavior (golden regression test required).
- Dispatch remains serial at the LLM call level; parallelism is only at the submission layer.
- Do NOT modify invite/signaling/role primitives.

Read the phase doc first, then implement.
```

### Agent 7B — Typing presence

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding debounced typing-presence broadcasts to poor-cli's multiplayer
server so every room member can see when others are composing a turn.

FIRST: Read docs/phase_go_07_multiplayer_backend.md, specifically the "Agent 7B" section.

CONTEXT:
- Existing connection state on RoomState in /Users/gongahkia/Desktop/coding/projects/poor-cli/poor_cli/multiplayer.py. Read lines 36–52 and 962–993.
- Feature is gated behind `multiplayer.features.typingPresence` (default false).

YOUR DELIVERABLES:
1. poor_cli/multiplayer_presence.py — PresenceTracker with debounce + periodic sweep.
2. poor_cli/multiplayer.py — start per-room sweep; handle `poor-cli/setTyping` inbound; broadcast `poor-cli/memberTyping`.
3. poor_cli/server/handlers/multiplayer.py — register `poor-cli/setTyping` and `poor-cli/listPresence`.
4. tests/test_multiplayer_presence.py — debounce correctness, disconnect cleanup, new-joiner snapshot.

CONSTRAINTS:
- Debounce defaults: 250 ms idle transition, 500 ms broadcast interval cap.
- No more than 2 broadcasts/sec per user.
- Feature flag off → setTyping returns method-not-found.
- Goroutine/task cleanup on room teardown.

Read the phase doc first, then implement.
```

### Agent 7C — Per-user message attribution

```
[AGENT PROMPT — copy/paste to your coding agent]

You are threading author identity (connectionId + displayName + role) through
every chat notification so clients can render per-user attribution in shared
transcripts.

FIRST: Read docs/phase_go_07_multiplayer_backend.md, specifically the "Agent 7C" section.

CONTEXT:
- Author-neutral notifications live in /Users/gongahkia/Desktop/coding/projects/poor-cli/poor_cli/server/handlers/chat_streaming.py lines 175–377.
- Queued requests today live in poor_cli/multiplayer.py (QueuedRequest at lines 1207–1227; broadcast at 1805–1843).
- Feature is gated behind `multiplayer.features.messageAttribution` (default false). When off, fields must still populate with a "local" identity so clients that always read them do not break.

YOUR DELIVERABLES:
1. poor_cli/multiplayer_attribution.py — helper returning `{authorConnectionId, authorDisplayName, authorRole}`.
2. poor_cli/multiplayer.py — QueuedRequest gains `author`; broadcast plumbs the tag.
3. poor_cli/server/handlers/chat_streaming.py — every streaming notification carries author fields.
4. Session history persistence — store author per message so reconnects restore attribution.
5. tests/test_multiplayer_attribution.py — multi-user correctness, single-player fallback, history replay.

CONSTRAINTS:
- Single-player mode must produce `authorConnectionId: "local"` so Go/Neovim clients that expect the fields do not break.
- Do NOT leak author fields into non-multiplayer contexts where clients explicitly opt out; use the helper.

Read the phase doc first, then implement.
```

### Agent 7D — Shared diff-review voting

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding a vote ledger to multiplayer diff review so multiple reviewers
can approve/reject each hunk, with configurable thresholds (majority, unanimous,
owner_only) gating the apply.

FIRST: Read docs/phase_go_07_multiplayer_backend.md, specifically the "Agent 7D" section.

CONTEXT:
- Agenda items on CollaborationSession at /Users/gongahkia/Desktop/coding/projects/poor-cli/poor_cli/multiplayer_session.py. Hunks/edits flow through poor_cli/server/handlers/diff_review.py.
- Feature is gated behind `multiplayer.features.diffVoting` (default false). When off, existing acceptHunk/rejectHunk behavior is unchanged.

YOUR DELIVERABLES:
1. poor_cli/multiplayer_voting.py — VoteLedger with majority/unanimous/owner_only threshold semantics.
2. poor_cli/multiplayer_session.py — AgendaItem.votes populated when feature on.
3. poor_cli/server/handlers/multiplayer.py — register `poor-cli/voteOnHunk`, `poor-cli/getHunkVotes`; broadcast `poor-cli/hunkVoteUpdated`.
4. poor_cli/server/handlers/diff_review.py — gate acceptHunk/acceptAll on vote status when feature on.
5. tests/test_multiplayer_voting.py — all three threshold modes, disconnect-during-vote recompute, clear-vote handling.

CONSTRAINTS:
- Thresholds recompute against currently-connected approved members on every recount.
- owner_only threshold preserves pre-change behavior exactly.

Read the phase doc first, then implement.
```

---

## Wave 8 — Multiplayer Neovim UI

**Agents: 3 (all parallel)**
**Reference document:** `docs/phase_go_08_multiplayer_neovim.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W7

### Agent 8A — Users side panel (Neovim)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a dedicated "users" side panel for the poor-cli Neovim plugin
that lists every room member with role, approval state, presence, and quick
actions.

FIRST: Read docs/phase_go_08_multiplayer_neovim.md, specifically the "Agent 8A" section.

CONTEXT:
- Existing collab panels for reference: /Users/gongahkia/Desktop/coding/projects/poor-cli/nvim-poor-cli/lua/poor-cli/collab.lua and multiplayer_room.lua.
- Plenary-based test harness in use; follow the existing pattern in nvim-poor-cli/tests/.
- Backend notifications already exist per W7: poor-cli/memberTyping, poor-cli/queueUpdated, poor-cli/collabMemberJoined, poor-cli/collabMemberLeft.

YOUR DELIVERABLES:
1. nvim-poor-cli/lua/poor-cli/users_panel.lua — fixed-width (32 cols) vertical split, two rows per member (name+role above, presence/status below), quick-action keymaps (a/d/x/r/p).
2. nvim-poor-cli/lua/poor-cli/rpc.lua — subscribe to memberTyping + queueUpdated notifications.
3. nvim-poor-cli/lua/poor-cli/init.lua — register :PoorCLIUsers command and <leader>pu keybind.
4. nvim-poor-cli/tests/users_panel_spec.lua — golden render, typing updates, approve flow, close/unsubscribe.

CONSTRAINTS:
- No RPC polling when the panel is closed.
- Subscriptions must be registered once at plugin init and survive panel close/reopen.

Read the phase doc first, then implement.
```

### Agent 8B — Typing + attribution in chat panel (Neovim)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are extending the existing chat panel to show per-user attribution
prefixes and a compact typing footer when multiplayer is active.

FIRST: Read docs/phase_go_08_multiplayer_neovim.md, specifically the "Agent 8B" section.

CONTEXT:
- Existing chat buffer and input hook in /Users/gongahkia/Desktop/coding/projects/poor-cli/nvim-poor-cli/lua/poor-cli/chat.lua.
- Author fields now populate on all streaming notifications from W7 Agent 7C.

YOUR DELIVERABLES:
1. nvim-poor-cli/lua/poor-cli/chat_attribution.lua — helpers format_author and format_typing_footer.
2. nvim-poor-cli/lua/poor-cli/chat.lua — render author prefix inline; footer below input; debounced setTyping on keystroke.
3. nvim-poor-cli/tests/chat_attribution_spec.lua — two-user rendering, typing footer lifecycle, single-player fallback.

CONSTRAINTS:
- Single-player mode must render identically to pre-change.
- setTyping calls capped to 1 per 250 ms per user.
- No new keymaps.

Read the phase doc first, then implement.
```

### Agent 8C — Diff-voting UI (Neovim)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding inline vote rows and vote keymaps to the existing Neovim diff
review pane so multiple reviewers can vote on each hunk.

FIRST: Read docs/phase_go_08_multiplayer_neovim.md, specifically the "Agent 8C" section.

CONTEXT:
- Existing diff review in /Users/gongahkia/Desktop/coding/projects/poor-cli/nvim-poor-cli/lua/poor-cli/diff_review.lua.
- Backend vote RPC added in W7 Agent 7D: poor-cli/voteOnHunk, poor-cli/hunkVoteUpdated.

YOUR DELIVERABLES:
1. nvim-poor-cli/lua/poor-cli/diff_voting.lua — render_vote_row and vote helpers.
2. nvim-poor-cli/lua/poor-cli/diff_review.lua — insert vote rows; add va/vr/vc keymaps; disable `a` on pending-vote hunks with a toast.
3. nvim-poor-cli/tests/diff_voting_spec.lua — majority, unanimous, owner_only paths; accept-blocked toast; clear-vote removal.

CONSTRAINTS:
- owner_only threshold hides vote row entirely (no visual change vs. pre-change).
- Minimal visual weight: one line per hunk, no borders.

Read the phase doc first, then implement.
```

---

## Wave 9 — Multiplayer Go UI

**Agents: 3 (all parallel)**
**Reference document:** `docs/phase_go_09_multiplayer_go.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W5 + W7

ADA-minimal discipline applies — no new persistent panes, no icons beyond existing glyphs, no color changes outside existing tokens.

### Agent 9A — Users side panel (Go)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are building a toggleable right-rail users panel in the Go TUI client. It
must be ADA-minimal: no borders, no fill, flush with the transcript, 28 cols.

FIRST: Read docs/phase_go_09_multiplayer_go.md, specifically the "Agent 9A" section.

CONTEXT:
- Existing Go client uses Bubbletea + lipgloss (Wave 5 landed by the time you start).
- Backend notifications: poor-cli/memberTyping, poor-cli/queueUpdated, poor-cli/collabMemberJoined, poor-cli/collabMemberLeft.
- State store pattern in internal/state/ — extend with MultiplayerState.

YOUR DELIVERABLES:
1. internal/tui/widgets/users_panel.go — rail widget rendering name+role/presence rows.
2. internal/tui/flows/users.go — subscription + action dispatch (approve/deny/kick/role/pass).
3. internal/protocol/multiplayer.go — add missing types if not already added by W7 trailer.
4. internal/tui/app.go — toggle + region adjustment (ctrl+u).
5. internal/tui/regions.go — right-rail math: when open, transcript reflows to width-28-1.
6. internal/tui/widgets/users_panel_test.go + flows/users_test.go.

CONSTRAINTS:
- Closed panel leaves zero footprint; no vestigial border.
- Auto-hide on terminals <100 cols with a toast.
- Display names truncated to 16 chars.

Read the phase doc first, then implement.
```

### Agent 9B — Presence + attribution (Go)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are wiring per-user attribution into the chat widget and adding a typing
footer above the status bar in the Go TUI client.

FIRST: Read docs/phase_go_09_multiplayer_go.md, specifically the "Agent 9B" section.

CONTEXT:
- Chat widget already renders "poor-cli ›" / "you ›" prefixes (per ADA-minimal decisions in phase_go_03).
- Backend Agent 7C threads authorConnectionId/authorDisplayName through every streaming notification.

YOUR DELIVERABLES:
1. internal/tui/flows/presence.go — subscribe to memberTyping; debounce local setTyping to every 250 ms.
2. internal/tui/flows/attribution.go — forward author fields to state; chat widget reads them for the prefix.
3. internal/tui/widgets/chat.go — render author prefix inline; `you ›` for local, `<name> ›` for remote author.
4. internal/tui/widgets/statusbar.go — add typing footer slot (single muted row, absent when nobody typing).
5. internal/tui/flows/chat.go — forward author fields from streamChunk into state updates.
6. Tests per agent file.

CONSTRAINTS:
- Local user's own turn always renders as `you ›`; never `<local-display-name> ›`.
- Typing footer is exactly one row tall and absent when empty.
- No emoji. No spinners.

Read the phase doc first, then implement.
```

### Agent 9C — Voting in diff modal (Go)

```
[AGENT PROMPT — copy/paste to your coding agent]

You are adding inline vote rows to the existing Go diff review modal. No new
modal, no borders, minimal visual weight.

FIRST: Read docs/phase_go_09_multiplayer_go.md, specifically the "Agent 9C" section.

CONTEXT:
- Existing diff modal in internal/tui/flows/diff.go (Wave 5D).
- Backend vote API from W7 Agent 7D: poor-cli/voteOnHunk, poor-cli/hunkVoteUpdated.

YOUR DELIVERABLES:
1. internal/tui/flows/voting.go — subscribe to hunkVoteUpdated; vote RPC wrapper.
2. internal/tui/flows/diff.go — insert vote row per hunk; va/vr/vc keymaps; disable y/n on pending-vote hunks; status-line toast when blocked.
3. internal/tui/flows/voting_test.go.

CONSTRAINTS:
- owner_only threshold hides vote row entirely.
- Vote row uses existing Success/Error/Muted tokens — no new colors.
- One line per hunk.

Read the phase doc first, then implement.
```

---

## Wave 10 — Go Minimalism Polish

**Agents: 3 (10A ∥ 10C in parallel; 10B serial after)**
**Reference document:** `docs/phase_go_10_go_minimalism_polish.md`
**Estimated time per agent:** 1–2 days
**Prerequisites:** W9

Final ship-gate for the Go TUI. Every earlier wave can leak chrome unintentionally; this wave hunts and removes it, tunes render cadence, and formalises empty states.

### Agent 10A — Visual audit & chrome strip

```
[AGENT PROMPT — copy/paste to your coding agent]

You are performing a visual audit of the Go TUI and stripping any non-ADA-minimal
chrome that earlier waves introduced. The target is ADA-level simplicity: no
boxes, no filled backgrounds, a maximum of six color tokens in use.

FIRST: Read docs/phase_go_10_go_minimalism_polish.md, specifically the "Agent 10A" section.

CONTEXT:
- Reference visual shown in the phase doc "Target aesthetic" section.
- Known offender list shown in the phase doc — start there.

YOUR DELIVERABLES:
1. docs/visual_audit.md — ASCII captures of 20+ user-visible states with a red/yellow/green checklist per state.
2. Surgical edits across internal/tui/widgets/, internal/tui/flows/, internal/theme/ to bring every failing state into compliance.
3. internal/tui/widgets/flush.go — shared FlushHeader/FlushList helpers replacing per-modal border drawing (if consolidation is warranted).
4. Updated golden snapshots for every affected widget test.

CONSTRAINTS:
- No new color tokens. The six allowed: Base, Muted, Focus, Success, Error, Warning.
- No emoji; icons limited to ●, ◌, ›, ·, ✓, ✗.
- Chat message gap is exactly one blank line.
- Modals may retain a minimal single border; chat area may not.

Read the phase doc first, then implement.
```

### Agent 10B — Perceived latency polish

```
[AGENT PROMPT — copy/paste to your coding agent]

You are measuring and tightening the Go client's perceived latency so keystrokes,
first-paint, and streaming feel instant on reference hardware.

FIRST: Read docs/phase_go_10_go_minimalism_polish.md, specifically the "Agent 10B" section.

CONTEXT:
- Targets: keystroke echo ≤8 ms; first stream byte ≤16 ms; render frame ≤8 ms at 200 tok/s; 60 Hz steady; splash→first paint ≤150 ms.
- Existing benchmarks from Wave 6D are the baseline.

YOUR DELIVERABLES:
1. bench/perceived_latency_test.go — harness driving Bubbletea at controlled tok/s, measuring the five targets.
2. docs/perceived_latency.md — before/after report with flamegraph links.
3. Source edits where pprof shows >1 ms hot paths:
   - render-on-demand skip when no state changed
   - markdown renderer tail-only repaint (confirm behavior)
   - state.Snapshot optimisations to avoid unnecessary copies
4. Enable trace logging via GOCLI_POOR_TRACE=1 writing to $XDG_STATE_HOME/gocli-poor/trace.jsonl.

CONSTRAINTS:
- No change behaves visually different at 60 Hz — optimizations must be invisible.
- All five metrics hit target on M-series laptop before merge.
- No regression in existing benchmarks.

Read the phase doc first, then implement.
```

### Agent 10C — Empty states & loading affordances

```
[AGENT PROMPT — copy/paste to your coding agent]

You are consolidating every empty/loading state in the Go TUI into a single
shared helper so the client always shows a minimal, tested, one-line muted hint
and never a blank screen or spinner.

FIRST: Read docs/phase_go_10_go_minimalism_polish.md, specifically the "Agent 10C" section.

CONTEXT:
- Ten empty states listed in the phase doc. "ready.", "connecting…", "disconnected — press ctrl+r", etc.
- Currently several flows ship ad-hoc strings — audit and replace.

YOUR DELIVERABLES:
1. internal/tui/empty_states.go — EmptyStateFor helper enumerating every state.
2. Edits in internal/tui/flows/* and internal/tui/widgets/* that currently render ad-hoc empty strings — route through the helper.
3. internal/tui/empty_states_test.go — verify each state renders correctly.

CONSTRAINTS:
- No spinner, progress bar, or animated indicator anywhere in the client.
- Empty-state text is always ≤1 line and always in the Muted token.
- The cursor on the prompt line is the only animated element.

Read the phase doc first, then implement.
```

---

## Notes for coordinators

- If you're driving this solo, tackle one wave at a time. Wave dependencies are listed per-wave.
- If you're driving with multiple agent sessions in parallel, the fastest path is described in "Fast path" above.
- Every phase doc is self-contained and can be read without the others.
- The orchestration-file conventions (copy-paste prompts and intra-wave collision tables) mirror the existing `docs/archive/implementation_waves.md` pattern. Every decision has been resolved in the phase docs; prompts are ready to dispatch without edits.

---

## Protocol quick-reference (read-only — authoritative version lives in `phase_go_01_protocol.md`)

| Aspect | Value |
|--------|-------|
| Transport | stdio, `Content-Length: N\r\n\r\n<utf-8 json>` |
| Entry command | `poor-cli-server --stdio` |
| Handshake | `initialize` (method) |
| Primary chat | `poor-cli/chatStreaming` (method) |
| Text delta field | `chunk` in notification params |
| Notification methods | `poor-cli/streamChunk`, `poor-cli/thinkingChunk`, `poor-cli/toolEvent`, `poor-cli/costUpdate`, `poor-cli/progress`, `poor-cli/permissionReq`, `tool.chunk` |
| Cancel | `poor-cli/cancelRequest` with `{requestId}` |
| Switch provider | `poor-cli/switchProvider` |
| List providers | `poor-cli/listProviders` |
| Sessions | `poor-cli/listSessions`, `poor-cli/switchSession` |
| Diff review | `poor-cli/listPendingEdits` / `acceptHunk` / `rejectHunk` / `regenerateHunk` / `acceptAll` / `rejectAll` |
| Cost | `poor-cli/getSessionCost`, `poor-cli/getContextPressure`, `poor-cli/getEconomySavings` |
| Trust model | local stdio trust; no wire auth; API keys passed at init or via `poor-cli/setApiKey` |
