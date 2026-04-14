package state

import "time"

const MaxMessages = 1000

type AppState struct {
	Messages        []Message
	InFlight        *InFlightRequest
	Provider        ProviderState
	Cost            CostState
	Session         SessionState
	Connection      ConnState
	ContextPressure ContextPressure
	Toasts          []ToastItem
}

type Message struct {
	ID        string
	Role      Role
	Content   string
	Streaming bool
	RequestID string
	Segments  []MarkdownSegment
	ToolCalls []ToolCall
	CreatedAt time.Time
}

type Role string

const (
	RoleUser      Role = "user"
	RoleAssistant Role = "assistant"
	RoleTool      Role = "tool"
	RoleSystem    Role = "system"
)

type MarkdownSegment struct {
	Text  string
	Plain string
	Width int
}

type ToolCall struct {
	EventID       string
	TurnID        string
	ToolCallID    string
	ToolName      string
	Status        string
	ArgsPreview   string
	ResultPreview string
	Error         string
	Chunks        []string
}

type InFlightRequest struct {
	RequestID string
	StartedAt time.Time
	CancelFn  func()
}

type InFlight = InFlightRequest

type ProviderState struct {
	Name  string
	Model string
	Caps  map[string]any
}

type CostState struct {
	SessionTotalUSD float64
	TotalUSD        float64
	InputTokens     int
	OutputTokens    int
	CacheReadTokens int
	Turns           int
	LastUpdatedAt   time.Time
}

type SessionState struct {
	ID          string
	Turns       int
	Checkpoints []Checkpoint
}

type Checkpoint struct {
	ID          string
	CreatedAt   string
	Description string
}

type ConnState struct {
	Phase     ConnPhase
	LastError string
}

type ConnPhase string

const (
	Disconnected ConnPhase = "disconnected"
	Starting     ConnPhase = "starting"
	Ready        ConnPhase = "ready"
	Error        ConnPhase = "error"
)

type ContextPressure struct {
	Tokens int
	Budget int
	Pct    float64
}

type ToastItem struct {
	Kind ToastKind
	Text string
	TTL  time.Duration
}

type ToastKind string

const (
	ToastInfo    ToastKind = "info"
	ToastWarning ToastKind = "warning"
	ToastError   ToastKind = "error"
	ToastSuccess ToastKind = "success"
)
