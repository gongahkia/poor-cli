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
	RequestID string
	Chunk     string
	Segments  []MarkdownSegment
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

type ActionUpdateCost struct {
	Snapshot  protocol.CostSnapshot
	UpdatedAt time.Time
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

type ActionCancelInFlight struct{}

func (ActionAppendMessage) actionMarker()         {}
func (ActionAppendChunk) actionMarker()           {}
func (ActionStartStream) actionMarker()           {}
func (ActionEndStream) actionMarker()             {}
func (ActionSetProvider) actionMarker()           {}
func (ActionUpdateCost) actionMarker()            {}
func (ActionSetConnection) actionMarker()         {}
func (ActionToast) actionMarker()                 {}
func (ActionReplaceMessages) actionMarker()       {}
func (ActionUpdateContextPressure) actionMarker() {}
func (ActionCancelInFlight) actionMarker()        {}
