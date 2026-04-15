# Phase Go 01 — Protocol Layer

**Priority:** Critical — everything above this wave depends on these bytes being correct.
**Agents:** 4 (all parallel, disjoint packages)
**Dependencies:** Wave 0
**Philosophy:** Spec-faithful first. Performance second. Ergonomics third. No protocol-level cleverness that deviates from what `nvim-poor-cli/lua/poor-cli/rpc.lua` already does — that is the working reference client.

---

## Reference sources (authoritative)

Every detail in this document was extracted directly from the poor-cli backend. If a conflict between this doc and the backend arises, the backend wins. File references assume the project root `/Users/gongahkia/Desktop/coding/projects/poor-cli/`.

| Concern | File | Lines |
|---------|------|-------|
| Framing, read/write loop | `poor_cli/server/transport.py` | 1–213 |
| Dispatcher, handler registry | `poor_cli/server/runtime.py` | 1–350 |
| `initialize` handler | `poor_cli/server/handlers/chat.py` | 34–216 |
| `poor-cli/chatStreaming` handler | `poor_cli/server/handlers/chat_streaming.py` | 175–377 |
| Cancel handler | `poor_cli/server/handlers/chat.py` | 384–388 |
| Provider handlers | `poor_cli/server/handlers/providers.py` | 9–200 |
| Diff review handlers | `poor_cli/server/handlers/diff_review.py` | full file |
| Timeline handlers | `poor_cli/server/handlers/timeline.py` | full file |
| Cost handlers | `poor_cli/server/handlers/cost.py` | full file |
| Sessions handlers | `poor_cli/server/handlers/sessions.py` | full file |
| MCP handlers | `poor_cli/server/handlers/mcp.py` | full file |
| Existing Lua client (reference behavior) | `nvim-poor-cli/lua/poor-cli/rpc.lua` | 1240–1321 |
| Entry point + flags | `poor_cli/server/cli.py` | 19–102 |
| Script name in pyproject | `pyproject.toml` | `[project.scripts]` |

---

## File-scope table (at-a-glance disjointness)

| Agent | Creates (new files) | Modifies (existing files) |
|-------|---------------------|---------------------------|
| 1A    | `internal/transport/codec.go`, `internal/transport/errors.go`, `internal/transport/codec_test.go`, `internal/transport/bench_test.go` | `internal/transport/doc.go` (replace stub) |
| 1B    | `internal/rpc/client.go`, `internal/rpc/pending.go`, `internal/rpc/ids.go`, `internal/rpc/client_test.go`, `internal/rpc/errors.go` | `internal/rpc/doc.go` |
| 1C    | `internal/protocol/*.go` (12 files — one per category), `internal/protocol/protocol_test.go` | `internal/protocol/doc.go` |
| 1D    | `internal/server/manager.go`, `internal/server/discovery.go`, `internal/server/health.go`, `internal/server/manager_test.go`, `internal/server/fake_server.go` | `internal/server/doc.go` |

### Intra-phase collisions

- **None.** Each agent owns a disjoint subpackage. No shared file edits.

---

## Framing (shared reference — every agent should read)

```
Header:  "Content-Length: " <decimal bytes> "\r\n\r\n"
         (ASCII, tolerant of \n\n fallback for non-spec clients)
Body:    UTF-8 encoded JSON, exactly <decimal bytes> long
```

- No `Content-Type` header is sent or required.
- Notifications (no `id`) are framed identically to responses.
- The server writes header and body in two syscalls; the client must accept either two writes or one coalesced write.
- Reader must tolerate arbitrary chunk boundaries (TCP/pipe semantics) — bytes may arrive one at a time.

Python ground-truth, `transport.py:74`:
```python
header_bytes = await reader.readuntil(b"\r\n\r\n")
```

Python ground-truth, `transport.py:188`:
```python
header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
```

Lua client behavior (same file referenced in orchestration):
```lua
local content = "Content-Length: " .. #json .. "\r\n\r\n" .. json
vim.fn.chansend(M.job_id, content)
```

---

## Agent 1A: Framed stdio transport codec

### What to build

Low-level I/O codec. No JSON. No JSON-RPC. Just framed message boundaries.

### Files

- `internal/transport/codec.go`
- `internal/transport/errors.go`
- `internal/transport/codec_test.go`
- `internal/transport/bench_test.go`
- `internal/transport/doc.go`

### API surface

```go
package transport

type Reader struct { /* ... */ }
func NewReader(r io.Reader) *Reader
// ReadMessage blocks until a complete framed message is available.
// Returns the raw JSON body bytes (no trailing newline).
func (r *Reader) ReadMessage() ([]byte, error)

type Writer struct { /* ... */ }
func NewWriter(w io.Writer) *Writer
// WriteMessage writes header + body atomically (single flush).
// Safe for concurrent calls (internal mutex).
func (w *Writer) WriteMessage(body []byte) error
```

### Implementation rules

1. **Reader state machine:**
   - Buffer unread bytes in an internal `[]byte` slice.
   - Search for `\r\n\r\n` or `\n\n` in buffer.
   - If not found, read more bytes (up to 64 KB header cap → else `ErrHeaderTooLarge`).
   - Parse `Content-Length` from header block (case-insensitive).
   - Wait for the body (buffered bytes + reads) to reach exactly `Content-Length` bytes.
   - Return those bytes; keep the remainder in the buffer for the next call.
2. **Writer serialization:**
   - Build the header as ASCII string.
   - Write header + body in a single `w.Write(buf)` call whenever possible to avoid partial-write interleaving on pipes.
   - Use a `sync.Mutex` so concurrent `WriteMessage` calls do not interleave frames.

### Errors

```go
var (
    ErrMissingContentLength = errors.New("transport: missing Content-Length header")
    ErrIncompleteHeader     = errors.New("transport: incomplete header")
    ErrIncompleteBody       = errors.New("transport: incomplete body")
    ErrHeaderTooLarge       = errors.New("transport: header exceeds 64 KB")
    ErrNegativeLength       = errors.New("transport: negative Content-Length")
)
```

### Tests

1. Round-trip 20 payloads (1 byte, 100 bytes, 1 KB, 10 KB, 100 KB, 1 MB) through an `io.Pipe`.
2. CRLF header — `Content-Length: 5\r\n\r\n{"a":1}`
3. LF fallback — `Content-Length: 5\n\n{"a":1}`
4. Multi-message pipelined — write 3 messages back-to-back; reader returns them in order.
5. Partial reads — wrap reader in a `slowReader` that returns 1 byte per Read.
6. Malformed header — extra fields, negative length, non-integer length → expected errors.
7. Truncated body (EOF mid-body) → `ErrIncompleteBody`.
8. Concurrent writers — 100 goroutines writing, assert no corruption.

### Benchmarks

- `BenchmarkWriter_1KB`, `BenchmarkWriter_100KB`
- `BenchmarkReader_1KB`, `BenchmarkReader_100KB`
- Target (on Apple M-series laptop): ≥ 1 GB/s for writer, ≥ 500 MB/s for reader. Report results in doc comment.

### Acceptance criteria

- [ ] All tests pass.
- [ ] Benchmarks report above thresholds.
- [ ] Zero allocations for payloads ≤ 16 KB (measured via `go test -bench -benchmem`).
- [ ] Linter green.
- [ ] Writer is safe under concurrent use (race detector clean).

### Rollback / risk

Minimal. Pure function library with unit tests.

---

## Agent 1B: JSON-RPC 2.0 client

### What to build

Request/response/notification multiplexer over the Agent 1A transport. Handles:
- request id generation
- pending-call registry (correlate response by id)
- server-push notification routing to subscribers
- clean shutdown on pipe close or error

### Files

- `internal/rpc/client.go`
- `internal/rpc/pending.go`
- `internal/rpc/ids.go`
- `internal/rpc/errors.go`
- `internal/rpc/client_test.go`
- `internal/rpc/doc.go`

### API surface

```go
package rpc

type Client struct { /* ... */ }

func NewClient(r io.Reader, w io.Writer, logger *slog.Logger) *Client

// Call sends a request, blocks until response or ctx expires.
// result may be nil (ignored). If non-nil, it is json.Unmarshal'd from the response's result field.
func (c *Client) Call(ctx context.Context, method string, params any, result any) error

// Notify sends a notification (no id, no response expected).
func (c *Client) Notify(method string, params any) error

// Subscribe registers a handler for notifications with the given method name.
// Returns an unsubscribe function. Handlers run on the reader goroutine — keep them fast.
func (c *Client) Subscribe(method string, handler NotificationHandler) (unsubscribe func())

// Start launches the reader goroutine. Must be called once before Call / Subscribe.
func (c *Client) Start()

// Close stops the reader goroutine, fails all pending calls with ErrClosed,
// and closes all subscriber channels.
func (c *Client) Close() error

type NotificationHandler func(params json.RawMessage)

type CallError struct {
    Code    int
    Message string
    Data    json.RawMessage
}
func (e *CallError) Error() string
```

### Wire-level message shapes

Request:
```json
{"jsonrpc":"2.0","id":42,"method":"poor-cli/chatStreaming","params":{...}}
```

Response (success):
```json
{"jsonrpc":"2.0","id":42,"result":{...}}
```

Response (error):
```json
{"jsonrpc":"2.0","id":42,"error":{"code":-32000,"message":"...","data":{...}}}
```

Notification (server → client, fire and forget):
```json
{"jsonrpc":"2.0","method":"poor-cli/streamChunk","params":{...}}
```

Rule: if the read message has an `id`, it's a response; otherwise notification. Confirmed in `runtime.py:285` (`if message.method and message.id is None: notification`).

### Reader goroutine pseudocode

```
for {
    body, err := reader.ReadMessage()
    if err != nil { fail-all-pending(err); return }
    parse body as json.RawMessage → discriminator
    if has "id" and ("result" or "error"):
        complete pending call by id
    else if has "method" and no "id":
        dispatch to subscribers by method
    else:
        log warn, continue
}
```

### Error taxonomy

```go
var ErrClosed = errors.New("rpc: client closed")
var ErrDuplicateSubscribe = errors.New("rpc: handler already registered")
```

`CallError` is returned when the server returns a JSON-RPC error. Standard codes:

| Code | Meaning |
|------|---------|
| -32700 | parse error |
| -32600 | invalid request |
| -32601 | method not found |
| -32602 | invalid params |
| -32603 | internal error |
| -32000..-32099 | application defined (poor-cli uses -32000 for generic errors with additional `error_code` in `data`) |

### Tests

1. Successful Call round trip using in-memory pipes.
2. Error response → `*CallError`.
3. Context cancel aborts pending call; id is released (not leaked).
4. 10 concurrent Calls with shuffled response order; all resolve correctly.
5. Notifications routed to multiple subscribers.
6. Unsubscribe correctness (no delivery after unsubscribe).
7. Transport pipe closed → all pending calls resolve with `ErrClosed`.
8. Malformed JSON → ignored, reader continues.

### Acceptance criteria

- [ ] All tests pass under `-race`.
- [ ] No goroutine leaks (verified with `goleak` in TestMain).
- [ ] Linter green.
- [ ] Reader recovers from malformed input without panicking.

---

## Agent 1C: Protocol types

### What to build

One Go struct per protocol message the client will ever send or receive. Covers:
- initialize
- chat + chat streaming
- all streaming notifications
- cancel
- providers / models
- diff review
- timeline
- cost
- sessions
- mcp

Plus a single `methods.go` file with string constants for all method names.

### Files

- `internal/protocol/init.go`
- `internal/protocol/chat.go`
- `internal/protocol/notifications.go`
- `internal/protocol/cancel.go`
- `internal/protocol/providers.go`
- `internal/protocol/diff.go`
- `internal/protocol/timeline.go`
- `internal/protocol/cost.go`
- `internal/protocol/sessions.go`
- `internal/protocol/mcp.go`
- `internal/protocol/methods.go`
- `internal/protocol/protocol_test.go`
- `internal/protocol/doc.go`

### Naming conventions

- Go identifier: `PascalCase`.
- JSON tag: `camelCase`, matching the Python / Lua wire names exactly.
- Optional fields: pointer type OR `omitempty`. Prefer pointer when "absent ≠ zero value" semantically matters (e.g. `MaxResponseTokens *int` — 0 is different from "unset").
- Time fields: use `int64` Unix millis on the wire; decode to `time.Time` via custom unmarshal if needed (most fields are strings or numbers, not times).

### Type catalog (exact shapes)

Below is the complete, authoritative catalog. Copy these directly into the appropriate files. Field names and types come from reading the referenced Python handlers.

#### init.go

```go
package protocol

type InitializeParams struct {
    Provider           string                 `json:"provider,omitempty"`
    Model              string                 `json:"model,omitempty"`
    APIKey             string                 `json:"apiKey,omitempty"`
    Streaming          *bool                  `json:"streaming,omitempty"`
    PermissionMode     string                 `json:"permissionMode,omitempty"`
    SandboxPreset      string                 `json:"sandboxPreset,omitempty"`
    ClientCapabilities map[string]any         `json:"clientCapabilities,omitempty"`
}

type InitializeResult struct {
    Capabilities Capabilities `json:"capabilities"`
}

type Capabilities struct {
    CompletionProvider          bool           `json:"completionProvider"`
    InlineCompletionProvider    bool           `json:"inlineCompletionProvider"`
    CompletionStreamingProvider bool           `json:"completionStreamingProvider"`
    ChatProvider                bool           `json:"chatProvider"`
    ChatStreamingProvider       bool           `json:"chatStreamingProvider"`
    FileOperations              bool           `json:"fileOperations"`
    PermissionMode              string         `json:"permissionMode"`
    SandboxPreset               string         `json:"sandboxPreset"`
    ServerLogPath               string         `json:"serverLogPath"`
    ProviderInfo                ProviderInfo   `json:"providerInfo"`
    GuardedFlow                 GuardedFlow    `json:"guardedFlow"`
    Security                    SecurityCaps   `json:"security"`
    RepoIndex                   *RepoIndex     `json:"repoIndex,omitempty"`
    NeedsAPIKey                 bool           `json:"needsApiKey,omitempty"`
    Message                     string         `json:"message,omitempty"`
}

type GuardedFlow struct {
    PermissionRequests bool `json:"permissionRequests"`
    PlanReview         bool `json:"planReview"`
}

type SecurityCaps struct {
    TrustedWorkspaceBoundary bool     `json:"trustedWorkspaceBoundary"`
    TrustedRoots             []string `json:"trustedRoots"`
}

type RepoIndex struct {
    Files   int    `json:"files"`
    Symbols int    `json:"symbols"`
    Status  string `json:"status"`
}
```

#### chat.go

```go
package protocol

type ChatStreamingParams struct {
    Message              string   `json:"message"`
    ContextFiles         []string `json:"contextFiles,omitempty"`
    PinnedContextFiles   []string `json:"pinnedContextFiles,omitempty"`
    ContextBudgetTokens  *int     `json:"contextBudgetTokens,omitempty"`
    MaxResponseTokens    *int     `json:"maxResponseTokens,omitempty"`
    RequestID            string   `json:"requestId,omitempty"`
    EditTurnID           string   `json:"editTurnId,omitempty"`
    SessionID            string   `json:"sessionId,omitempty"`
}

type ChatResult struct {
    Content string `json:"content"`
    Role    string `json:"role"` // "assistant"
}
```

#### notifications.go

```go
package protocol

type StreamChunk struct {
    RequestID string `json:"requestId"`
    Chunk     string `json:"chunk"`
    Done      bool   `json:"done"`
    Reason    string `json:"reason,omitempty"`
}

type ThinkingChunk struct {
    RequestID string `json:"requestId"`
    Chunk     string `json:"chunk"`
}

type ToolEvent struct {
    RequestID     string         `json:"requestId"`
    EventType     string         `json:"eventType"` // "tool_call_start" | "tool_result"
    ToolName      string         `json:"toolName"`
    ToolArgs      map[string]any `json:"toolArgs"`
    ToolResult    any            `json:"toolResult,omitempty"`
    CallID        string         `json:"callId,omitempty"`
    Diff          string         `json:"diff,omitempty"`
    Paths         []string       `json:"paths,omitempty"`
    CheckpointID  string         `json:"checkpointId,omitempty"`
    Changed       *bool          `json:"changed,omitempty"`
    Message       string         `json:"message,omitempty"`
    OutputFilter  map[string]any `json:"outputFilter,omitempty"`
    OriginalSize  int            `json:"originalSize,omitempty"`
    FilteredSize  int            `json:"filteredSize,omitempty"`
}

type CostUpdate struct {
    RequestID         string  `json:"requestId"`
    InputTokens       int     `json:"inputTokens"`
    OutputTokens      int     `json:"outputTokens"`
    EstimatedCost     float64 `json:"estimatedCost"`
    ModelName         string  `json:"modelName,omitempty"`
    CacheReadTokens   int     `json:"cacheReadTokens,omitempty"`
    CacheWriteTokens  int     `json:"cacheWriteTokens,omitempty"`
}

type Progress struct {
    RequestID      string `json:"requestId"`
    Phase          string `json:"phase"`
    Message        string `json:"message"`
    IterationIndex *int   `json:"iterationIndex,omitempty"`
    IterationCap   *int   `json:"iterationCap,omitempty"`
}

type PermissionReq struct {
    RequestID   string         `json:"requestId"`
    RequestKey  string         `json:"requestKey"`
    ToolName    string         `json:"toolName"`
    Description string         `json:"description"`
    Details     map[string]any `json:"details,omitempty"`
    Rationale   string         `json:"rationale,omitempty"`
}

type PermissionRes struct {
    RequestID      string `json:"requestId"`
    RequestKey     string `json:"requestKey"`
    Decision       string `json:"decision"` // "allow" | "deny" | "allow_session" | "allow_always"
    RememberScope  string `json:"rememberScope,omitempty"`
}

type ToolChunk struct {
    EventID    string `json:"eventId"`
    TurnID     string `json:"turnId"`
    ToolCallID string `json:"toolCallId"`
    ToolName   string `json:"toolName"`
    Chunk      string `json:"chunk"`
}

type InlineChunk struct {
    RequestID string `json:"requestId"`
    Chunk     string `json:"chunk"`
    Done      bool   `json:"done"`
}
```

#### cancel.go

```go
package protocol

type CancelParams struct {
    RequestID string `json:"requestId"`
}

type CancelResult struct {
    Success   bool   `json:"success"`
    RequestID string `json:"requestId,omitempty"`
}
```

#### providers.go

```go
package protocol

type ProviderInfo struct {
    Name           string   `json:"name"`
    Model          string   `json:"model"`
    Tier           string   `json:"tier,omitempty"`
    CostPer1kIn    *float64 `json:"costPer1kIn,omitempty"`
    CostPer1kOut   *float64 `json:"costPer1kOut,omitempty"`
    ContextWindow  int      `json:"contextWindow,omitempty"`
    Streaming      bool     `json:"streaming,omitempty"`
    Vision         bool     `json:"vision,omitempty"`
    FunctionCall   bool     `json:"functionCall,omitempty"`
}

type SwitchProviderParams struct {
    Provider string `json:"provider"`
    Model    string `json:"model,omitempty"`
}

type SwitchProviderResult struct {
    Success  bool         `json:"success"`
    Provider ProviderInfo `json:"provider"`
    Error    string       `json:"error,omitempty"`
}

type ListProvidersResult map[string]ProviderDetail

type ProviderDetail struct {
    Available   bool                        `json:"available"`
    Ready       bool                        `json:"ready"`
    StatusLabel string                      `json:"statusLabel"`
    Models      []string                    `json:"models"`
    ModelTiers  map[string]ModelTierDetail  `json:"modelTiers,omitempty"`
    Capabilities []string                   `json:"capabilities,omitempty"`
}

type ModelTierDetail struct {
    Tier          string  `json:"tier"`
    Cost1kIn      float64 `json:"cost1kIn"`
    Cost1kOut     float64 `json:"cost1kOut"`
    SpeedRank     int     `json:"speedRank,omitempty"`
    ContextWindow int     `json:"contextWindow,omitempty"`
}

type SetAPIKeyParams struct {
    Provider             string `json:"provider"`
    APIKey               string `json:"apiKey"`
    Persist              *bool  `json:"persist,omitempty"`
    ReloadActiveProvider *bool  `json:"reloadActiveProvider,omitempty"`
}

type SetAPIKeyResult struct {
    Success bool   `json:"success"`
    Error   string `json:"error,omitempty"`
}
```

#### diff.go

```go
package protocol

type DiffListResult struct {
    Edits []PendingEdit `json:"edits"`
}

type PendingEdit struct {
    ID       string   `json:"id"`
    Path     string   `json:"path"`
    Hunks    []Hunk   `json:"hunks"`
    Summary  string   `json:"summary,omitempty"`
    ToolName string   `json:"toolName,omitempty"`
    CallID   string   `json:"callId,omitempty"`
}

type Hunk struct {
    ID      string `json:"id"`
    Header  string `json:"header"`
    Body    string `json:"body"`
    Added   int    `json:"added"`
    Removed int    `json:"removed"`
}

type DiffAcceptParams  struct { EditID, HunkID string `json:"editId"` } // adjust to real shape
type DiffRejectParams  struct { EditID, HunkID string `json:"editId"` }
type DiffRegenParams   struct { EditID string `json:"editId"`; Instruction string `json:"instruction,omitempty"` }
```

(When the agent opens `diff_review.py` it should replace these stubs with the exact shape. Ship-compliant shape > doc guess.)

#### timeline.go

```go
package protocol

type TimelineEvent struct {
    ID         string         `json:"id"`
    TurnID     string         `json:"turnId"`
    Type       string         `json:"type"` // tool_call_start, tool_result, chunk, ...
    ToolName   string         `json:"toolName,omitempty"`
    Status     string         `json:"status,omitempty"`
    StartedAt  int64          `json:"startedAt,omitempty"`
    EndedAt    int64          `json:"endedAt,omitempty"`
    Payload    map[string]any `json:"payload,omitempty"`
}

type TimelineListResult struct {
    Events []TimelineEvent `json:"events"`
}
```

#### cost.go

```go
package protocol

type CostSnapshot struct {
    SessionCost     float64        `json:"sessionCost"`
    TotalCost       float64        `json:"totalCost"`
    InputTokens     int            `json:"inputTokens"`
    OutputTokens    int            `json:"outputTokens"`
    CacheReadTokens int            `json:"cacheReadTokens"`
    PerProvider     map[string]any `json:"perProvider,omitempty"`
}

type ContextPressure struct {
    UsedTokens   int     `json:"usedTokens"`
    BudgetTokens int     `json:"budgetTokens"`
    Percent      float64 `json:"percent"`
    Warning      string  `json:"warning,omitempty"`
}

type ContextBreakdown struct {
    ByCategory map[string]int `json:"byCategory"`
    Total      int            `json:"total"`
}

type SavingsSnapshot struct {
    TotalSavedUSD   float64            `json:"totalSavedUsd"`
    ByStrategy      map[string]float64 `json:"byStrategy"`
    LastUpdatedAt   int64              `json:"lastUpdatedAt,omitempty"`
}
```

#### sessions.go

```go
package protocol

type ListSessionsResult struct {
    Sessions []SessionSummary `json:"sessions"`
}

type SessionSummary struct {
    ID           string  `json:"id"`
    Title        string  `json:"title,omitempty"`
    MessageCount int     `json:"messageCount"`
    CostUSD      float64 `json:"costUsd"`
    StartedAt    int64   `json:"startedAt"`
    UpdatedAt    int64   `json:"updatedAt"`
}

type SwitchSessionParams struct {
    SessionID string `json:"sessionId"`
}
```

#### mcp.go

```go
package protocol

type McpListResult struct {
    Servers []McpServer `json:"servers"`
}

type McpServer struct {
    Name      string   `json:"name"`
    Transport string   `json:"transport"`
    Enabled   bool     `json:"enabled"`
    Tools     []string `json:"tools,omitempty"`
    Status    string   `json:"status,omitempty"`
}

type McpToggleParams struct {
    Name    string `json:"name"`
    Enabled bool   `json:"enabled"`
}
```

#### methods.go

```go
package protocol

const (
    // lifecycle
    MethodInitialize      = "initialize"
    MethodShutdown        = "shutdown"

    // chat
    MethodChat            = "poor-cli/chat"
    MethodChatStreaming   = "poor-cli/chatStreaming"
    MethodInlineComplete  = "poor-cli/inlineComplete"
    MethodClearHistory    = "poor-cli/clearHistory"
    MethodCancelRequest   = "poor-cli/cancelRequest"

    // streaming notifications (server → client)
    MethodStreamChunk     = "poor-cli/streamChunk"
    MethodThinkingChunk   = "poor-cli/thinkingChunk"
    MethodToolEvent       = "poor-cli/toolEvent"
    MethodToolChunk       = "tool.chunk"
    MethodInlineChunk     = "poor-cli/inlineChunk"
    MethodCostUpdate      = "poor-cli/costUpdate"
    MethodProgress        = "poor-cli/progress"
    MethodPermissionReq   = "poor-cli/permissionReq"

    // client → server notifications
    MethodPermissionRes   = "poor-cli/permissionRes"

    // providers
    MethodGetProviderInfo = "poor-cli/getProviderInfo"
    MethodListProviders   = "poor-cli/listProviders"
    MethodSwitchProvider  = "poor-cli/switchProvider"
    MethodSetAPIKey       = "poor-cli/setApiKey"

    // diff review
    MethodListPendingEdits = "poor-cli/listPendingEdits"
    MethodPreviewEdit      = "poor-cli/previewEdit"
    MethodStageEdit        = "poor-cli/stageEdit"
    MethodAcceptHunk       = "poor-cli/acceptHunk"
    MethodRejectHunk       = "poor-cli/rejectHunk"
    MethodRegenerateHunk   = "poor-cli/regenerateHunk"
    MethodAcceptAll        = "poor-cli/acceptAll"
    MethodRejectAll        = "poor-cli/rejectAll"

    // timeline
    MethodTimelineList     = "timeline.list"
    MethodTimelineCancel   = "timeline.cancel"
    MethodTimelineRetry    = "timeline.retry"
    MethodTimelineDismiss  = "timeline.dismiss"

    // cost / savings
    MethodGetSessionCost      = "poor-cli/getSessionCost"
    MethodCostSnapshot        = "cost.snapshot"
    MethodGetEconomySavings   = "poor-cli/getEconomySavings"
    MethodSavingsSnapshot     = "savings.snapshot"
    MethodGetCacheStats       = "poor-cli/getCacheStats"
    MethodGetContextPressure  = "poor-cli/getContextPressure"
    MethodGetContextBreakdown = "poor-cli/getContextBreakdown"
    MethodEstimateCost        = "poor-cli/estimateCost"
    MethodCompareModelCost    = "poor-cli/compareModelCost"

    // sessions
    MethodListSessions   = "poor-cli/listSessions"
    MethodSwitchSession  = "poor-cli/switchSession"
    MethodListHistory    = "poor-cli/listHistory"
    MethodListCheckpoints = "poor-cli/listCheckpoints"

    // mcp
    MethodMcpList    = "mcp.list"
    MethodMcpToggle  = "mcp.toggle"
    MethodMcpHealth  = "mcp.health"
    MethodMcpTest    = "mcp.test"
    MethodMcpEdit    = "mcp.edit"

    // context
    MethodContextEngine = "context.engine"
    MethodContextExplain = "context.explain"
    MethodContextStatus = "poor-cli/contextStatus"
)
```

### Tests (`protocol_test.go`)

For each struct, round-trip marshal/unmarshal test using a realistic payload. Sample payloads captured from logging the Python server during a normal chat turn.

Example:
```go
func TestStreamChunk_RoundTrip(t *testing.T) {
    input := []byte(`{"requestId":"r1","chunk":"hello","done":false}`)
    var sc protocol.StreamChunk
    if err := json.Unmarshal(input, &sc); err != nil { t.Fatal(err) }
    if sc.Chunk != "hello" || sc.RequestID != "r1" || sc.Done { t.Fatalf("wrong decode: %+v", sc) }
    out, _ := json.Marshal(sc)
    if string(out) != `{"requestId":"r1","chunk":"hello","done":false}` { /* ... */ }
}
```

### Acceptance criteria

- [ ] Every method in `methods.go` is referenced somewhere else in `internal/protocol/` or has a struct pair defined.
- [ ] All round-trip tests pass with byte-exact output for canonical payloads.
- [ ] No `interface{}` / `any` leaks into exported API beyond `map[string]any` for genuinely-polymorphic fields (tool args, payloads).
- [ ] `go doc ./internal/protocol` reads clean.

### Notes

- If you find fields during implementation that the backend uses but this doc missed, add them. This doc is a scaffold; the Python handler is the source of truth.
- If a method name string here mismatches what the Python registers (`@register(...)`), the Python registration wins.

---

## Agent 1D: Server process lifecycle

### What to build

Owns the child `poor-cli-server --stdio` process. Exposes stdin/stdout pipes to Agent 1A. Handles startup detection, stderr capture, graceful + forced shutdown, and optional health probes.

### Files

- `internal/server/manager.go`
- `internal/server/discovery.go`
- `internal/server/health.go`
- `internal/server/manager_test.go`
- `internal/server/fake_server.go` — a small echo server binary used for tests
- `internal/server/doc.go`

### API surface

```go
package server

type Config struct {
    BinaryPath string            // optional override; empty → discovery
    Args       []string          // extra flags beyond --stdio
    Env        map[string]string // additional env vars merged with os.Environ
    Cwd        string            // working dir; empty → current
    Logger     *slog.Logger
    ReadyTimeout time.Duration   // default 3s
}

type Manager struct { /* ... */ }

func NewManager(cfg Config) *Manager
func (m *Manager) Start(ctx context.Context) error
func (m *Manager) Stdin() io.Writer
func (m *Manager) Stdout() io.Reader
func (m *Manager) Wait() error
func (m *Manager) Shutdown(ctx context.Context) error
func (m *Manager) TailStderr(n int) []string
func (m *Manager) PID() int
```

### Discovery (discovery.go)

```go
func ResolveBinary(override string) (string, error)
```

Precedence:
1. `override` if non-empty (must exist and be executable).
2. `POOR_CLI_SERVER_PATH` env var.
3. `exec.LookPath("poor-cli-server")`.
4. `exec.LookPath("poor-cli")` (fallback — `poor-cli` as a CLI also supports `--stdio` subcommand in older versions; emit a warning).
5. Error with helpful message including install instructions.

### Stderr handling

- Read continuously on a goroutine — otherwise pipe fills and blocks the child.
- Keep a ring buffer of last N lines (default 500) for `TailStderr`.
- Optional: tee to a file if `cfg.Env["POOR_CLI_SERVER_LOG_FILE"]` is set — the server already writes there when that env is present.

### Shutdown protocol

1. Send an `rpc.Notify("shutdown", nil)` if the client is still usable (optional; Agent 5A wires this).
2. Wait up to 3 seconds for the process to exit naturally.
3. Send `SIGTERM`.
4. Wait up to 3 more seconds.
5. Send `SIGKILL`.
6. Always release pipe handles.

### Health probes (health.go)

- Optional periodic `poor-cli/getProviderInfo` every 60s.
- Three consecutive failures → Manager state = Unhealthy; Wave 5 flows surface a Toast.

### Fake server (fake_server.go)

A small Go program built into a test-only binary that speaks the framing protocol well enough to round-trip a scripted sequence of notifications. Used by tests in this wave AND by Wave 5 integration tests.

```go
//go:build fakes

package server

// FakeServerBinaryPath returns the path to the fake server binary.
// Tests use this instead of resolving the real poor-cli-server.
func FakeServerBinaryPath(t *testing.T) string { /* build via go tool */ }
```

### Tests

1. `TestDiscovery_PrefersOverride` — explicit path wins.
2. `TestDiscovery_FallsBackToEnv` — env var works.
3. `TestDiscovery_FallsBackToPATH` — temp bin added to PATH.
4. `TestDiscovery_MissingBinary` — helpful error.
5. `TestManager_StartupReady` — fake server writes a readiness line; Start returns within ReadyTimeout.
6. `TestManager_ShutdownEscalates` — fake server ignores SIGTERM; SIGKILL fires after 3s.
7. `TestManager_StderrRingBuffer` — fake server emits 1000 log lines; TailStderr(100) returns last 100.
8. `TestManager_RestartIfCrashed` — optional helper.

### Acceptance criteria

- [ ] All tests pass on Linux and macOS.
- [ ] No goroutine leaks.
- [ ] Process group cleanup on Windows (build tag; only require Linux/macOS for v1).
- [ ] Shutdown always returns within 7 seconds.

### Rollback / risk

Low. Isolated package; failures are scoped to the client binary.

### Notes

- `--host` / `--bridge` multiplayer flags: supported via a separate `ServerMode` field (see phase_go_07 multiplayer backend wave). v1 client-process boots in stdio mode; multiplayer flows use the dedicated signaling path.
- Readiness detection: stderr-log-only with a 500ms grace window; actual readiness is proven by `initialize` returning successfully (Wave 5 responsibility).
