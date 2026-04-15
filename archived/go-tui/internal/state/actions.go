package state

import (
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

type Action interface {
	actionMarker()
}

type ActionAppendMessage struct {
	Msg Message
}

type ActionAppendChunk struct {
	RequestID          string
	Chunk              string
	Segments           []MarkdownSegment
	AuthorConnectionID string
	AuthorDisplayName  string
	AuthorRole         string
}

type ActionAppendThinking struct {
	RequestID          string
	Chunk              string
	AuthorConnectionID string
	AuthorDisplayName  string
	AuthorRole         string
}

type ActionAppendToolCall struct {
	RequestID          string
	Call               ToolCall
	AuthorConnectionID string
	AuthorDisplayName  string
	AuthorRole         string
}

type ActionStartStream struct {
	RequestID      string
	AssistantMsgID string
	StartedAt      time.Time
	CancelFn       func()
}

type ActionEndStream struct {
	RequestID string
	Reason    string
}

type ActionSetProvider struct {
	Info protocol.ProviderInfo
}

type ActionSetSession struct {
	SessionID   string
	Turns       int
	Checkpoints []Checkpoint
}

type ActionUpdateCost struct {
	Snapshot  protocol.CostSnapshot
	UpdatedAt time.Time
}

type ActionSetProgress struct {
	Progress           ProgressState
	AuthorConnectionID string
	AuthorDisplayName  string
	AuthorRole         string
}

type ActionSetConnection struct {
	Phase ConnPhase
	Err   string
}

type ActionToast struct {
	Kind ToastKind
	Text string
	TTL  time.Duration
}

type ActionReplaceMessages struct {
	Messages []Message
}

type ActionUpdateContextPressure struct {
	Pressure ContextPressure
}

type ActionSetFileCatalog struct {
	Catalog FileCatalog
}

type ActionSetMultiplayer struct {
	Multiplayer MultiplayerState
}

type ActionUpdateMemberTyping struct {
	ConnectionID string
	DisplayName  string
	Typing       bool
	At           time.Time
}

type ActionUpdateQueue struct {
	Queue []QueueItem
}

type ActionUpdateHunkVotes struct {
	Update protocol.HunkVoteUpdate
}

type ActionCancelInFlight struct{}

type ActionSetMessageAuthor struct {
	RequestID          string
	AuthorConnectionID string
	AuthorDisplayName  string
	AuthorRole         string
}

func (ActionAppendMessage) actionMarker()         {}
func (ActionAppendChunk) actionMarker()           {}
func (ActionAppendThinking) actionMarker()        {}
func (ActionAppendToolCall) actionMarker()        {}
func (ActionStartStream) actionMarker()           {}
func (ActionEndStream) actionMarker()             {}
func (ActionSetProvider) actionMarker()           {}
func (ActionSetSession) actionMarker()            {}
func (ActionUpdateCost) actionMarker()            {}
func (ActionSetProgress) actionMarker()           {}
func (ActionSetConnection) actionMarker()         {}
func (ActionToast) actionMarker()                 {}
func (ActionReplaceMessages) actionMarker()       {}
func (ActionUpdateContextPressure) actionMarker() {}
func (ActionSetFileCatalog) actionMarker()        {}
func (ActionSetMultiplayer) actionMarker()        {}
func (ActionUpdateMemberTyping) actionMarker()    {}
func (ActionUpdateQueue) actionMarker()           {}
func (ActionUpdateHunkVotes) actionMarker()       {}
func (ActionCancelInFlight) actionMarker()        {}
func (ActionSetMessageAuthor) actionMarker()      {}
