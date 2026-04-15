package state

import (
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

const MaxMessages = 1000

type AppState struct {
	Revision        uint64
	Messages        []Message
	InFlight        *InFlightRequest
	Progress        *ProgressState
	Provider        ProviderState
	Cost            CostState
	Session         SessionState
	Connection      ConnState
	ContextPressure ContextPressure
	FileCatalog     FileCatalog
	Multiplayer     MultiplayerState
	Toasts          []ToastItem
}

type Message struct {
	ID                 string
	Role               Role
	Content            string
	Streaming          bool
	RequestID          string
	AuthorConnectionID string
	AuthorDisplayName  string
	AuthorRole         string
	Segments           []MarkdownSegment
	ToolCalls          []ToolCall
	Thinking           string
	Progress           string
	CreatedAt          time.Time
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

type ProgressState struct {
	RequestID      string
	Phase          string
	Message        string
	IterationIndex *int
	IterationCap   *int
}

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

type FileCatalog struct {
	Files         []FileCatalogFile
	Loading       bool
	LastUpdatedAt time.Time
}

type FileCatalogFile struct {
	Path     string
	Language string
	Score    float64
}

type MultiplayerState struct {
	Enabled           bool
	RoomName          string
	LocalConnectionID string
	LocalDisplayName  string
	Members           []Member
	Typing            map[string]bool
	Queue             []QueueItem
	HunkVotes         map[string]protocol.HunkVoteUpdate
	PresenceAt        time.Time
}

type Member struct {
	ConnectionID  string
	DisplayName   string
	Role          string
	ApprovalState string
	HandRaised    bool
	QueuePosition int
	VotesCast     int
	VotesPending  int
}

type QueueItem struct {
	ConnectionID string
	Position     int
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
