package state

import (
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

func Reduce(st AppState, action Action) AppState {
	switch a := action.(type) {
	case ActionAppendMessage:
		next := cloneAppState(st)
		next.Messages = trimMessages(append(next.Messages, cloneMessage(a.Msg)))
		return next
	case ActionAppendChunk:
		next := cloneAppState(st)
		for i := len(next.Messages) - 1; i >= 0; i-- {
			msg := &next.Messages[i]
			if msg.RequestID == a.RequestID && msg.Streaming {
				msg.Content += a.Chunk
				msg.Segments = append(msg.Segments, cloneSegments(a.Segments)...)
				return next
			}
		}
		return next
	case ActionStartStream:
		next := cloneAppState(st)
		next.InFlight = &InFlightRequest{RequestID: a.RequestID, StartedAt: a.StartedAt, CancelFn: a.CancelFn}
		if a.AssistantMsgID == "" {
			return next
		}
		for i := len(next.Messages) - 1; i >= 0; i-- {
			msg := &next.Messages[i]
			if msg.ID == a.AssistantMsgID {
				msg.RequestID = a.RequestID
				msg.Streaming = true
				return next
			}
		}
		next.Messages = trimMessages(append(next.Messages, Message{
			ID:        a.AssistantMsgID,
			Role:      RoleAssistant,
			RequestID: a.RequestID,
			Streaming: true,
			CreatedAt: a.StartedAt,
		}))
		return next
	case ActionEndStream:
		next := cloneAppState(st)
		if next.InFlight != nil && next.InFlight.RequestID == a.RequestID {
			next.InFlight = nil
		}
		for i := len(next.Messages) - 1; i >= 0; i-- {
			if next.Messages[i].RequestID == a.RequestID && next.Messages[i].Streaming {
				next.Messages[i].Streaming = false
				break
			}
		}
		return next
	case ActionSetProvider:
		next := cloneAppState(st)
		next.Provider = ProviderState{Name: a.Info.Name, Model: a.Info.Model, Caps: cloneMap(a.Info.Capabilities)}
		return next
	case ActionUpdateCost:
		next := cloneAppState(st)
		next.Cost = costStateFromSnapshot(a.Snapshot, a.UpdatedAt)
		return next
	case ActionSetConnection:
		next := cloneAppState(st)
		next.Connection = ConnState{Phase: a.Phase, LastError: a.Err}
		return next
	case ActionToast:
		next := cloneAppState(st)
		next.Toasts = append(next.Toasts, ToastItem{Kind: a.Kind, Text: a.Text, TTL: a.TTL})
		return next
	case ActionReplaceMessages:
		next := cloneAppState(st)
		next.Messages = trimMessages(cloneMessages(a.Messages))
		return next
	case ActionUpdateContextPressure:
		next := cloneAppState(st)
		next.ContextPressure = a.Pressure
		return next
	case ActionCancelInFlight:
		next := cloneAppState(st)
		next.InFlight = nil
		return next
	default:
		return cloneAppState(st)
	}
}

func costStateFromSnapshot(snapshot protocol.CostSnapshot, updatedAt time.Time) CostState {
	inputTokens := firstNonZero(snapshot.InputTokens, snapshot.Summary.InputTokens, snapshot.Summary.InputTokensCamel)
	outputTokens := firstNonZero(snapshot.OutputTokens, snapshot.Summary.OutputTokens, snapshot.Summary.OutputTokensCamel)
	cacheReadTokens := firstNonZero(snapshot.CacheReadTokens, snapshot.Summary.CacheReadTokens, snapshot.Summary.CacheReadInputTokens, snapshot.Summary.CacheReadInputTokensCamel)
	return CostState{
		SessionTotalUSD: firstNonZeroFloat(snapshot.Session.TotalUSD, snapshot.SessionCost, snapshot.Summary.SessionCost),
		TotalUSD:        firstNonZeroFloat(snapshot.TotalCost, snapshot.Summary.TotalCost, snapshot.Summary.EstimatedCostUSD, snapshot.Summary.EstimatedCost),
		InputTokens:     inputTokens,
		OutputTokens:    outputTokens,
		CacheReadTokens: cacheReadTokens,
		Turns:           firstNonZero(snapshot.Session.Turns, snapshot.Summary.RequestCount, snapshot.Summary.RequestCountCamel),
		LastUpdatedAt:   updatedAt,
	}
}

func trimMessages(messages []Message) []Message {
	if len(messages) <= MaxMessages {
		return messages
	}
	out := make([]Message, MaxMessages)
	copy(out, messages[len(messages)-MaxMessages:])
	return out
}

func cloneAppState(st AppState) AppState {
	next := st
	next.Messages = cloneMessages(st.Messages)
	if st.InFlight != nil {
		inFlight := *st.InFlight
		next.InFlight = &inFlight
	}
	next.Provider.Caps = cloneMap(st.Provider.Caps)
	next.Session.Checkpoints = cloneCheckpoints(st.Session.Checkpoints)
	next.Toasts = cloneToasts(st.Toasts)
	return next
}

func cloneMessages(messages []Message) []Message {
	if messages == nil {
		return nil
	}
	out := make([]Message, len(messages))
	for i, msg := range messages {
		out[i] = cloneMessage(msg)
	}
	return out
}

func cloneMessage(msg Message) Message {
	msg.Segments = cloneSegments(msg.Segments)
	msg.ToolCalls = cloneToolCalls(msg.ToolCalls)
	return msg
}

func cloneSegments(segments []MarkdownSegment) []MarkdownSegment {
	if segments == nil {
		return nil
	}
	out := make([]MarkdownSegment, len(segments))
	copy(out, segments)
	return out
}

func cloneToolCalls(calls []ToolCall) []ToolCall {
	if calls == nil {
		return nil
	}
	out := make([]ToolCall, len(calls))
	for i, call := range calls {
		out[i] = call
		if call.Chunks != nil {
			out[i].Chunks = append([]string(nil), call.Chunks...)
		}
	}
	return out
}

func cloneCheckpoints(checkpoints []Checkpoint) []Checkpoint {
	if checkpoints == nil {
		return nil
	}
	out := make([]Checkpoint, len(checkpoints))
	copy(out, checkpoints)
	return out
}

func cloneToasts(toasts []ToastItem) []ToastItem {
	if toasts == nil {
		return nil
	}
	out := make([]ToastItem, len(toasts))
	copy(out, toasts)
	return out
}

func cloneMap(in map[string]any) map[string]any {
	if in == nil {
		return nil
	}
	out := make(map[string]any, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

func firstNonZero(values ...int) int {
	for _, v := range values {
		if v != 0 {
			return v
		}
	}
	return 0
}

func firstNonZeroFloat(values ...float64) float64 {
	for _, v := range values {
		if v != 0 {
			return v
		}
	}
	return 0
}
