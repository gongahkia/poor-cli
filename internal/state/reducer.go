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
				applyAuthor(msg, a.AuthorConnectionID, a.AuthorDisplayName, a.AuthorRole)
				markMultiplayerForAuthor(&next, a.AuthorConnectionID)
				return next
			}
		}
		return next
	case ActionAppendThinking:
		next := cloneAppState(st)
		for i := len(next.Messages) - 1; i >= 0; i-- {
			msg := &next.Messages[i]
			if msg.RequestID == a.RequestID && msg.Streaming {
				msg.Thinking += a.Chunk
				applyAuthor(msg, a.AuthorConnectionID, a.AuthorDisplayName, a.AuthorRole)
				markMultiplayerForAuthor(&next, a.AuthorConnectionID)
				return next
			}
		}
		return next
	case ActionAppendToolCall:
		next := cloneAppState(st)
		for i := len(next.Messages) - 1; i >= 0; i-- {
			msg := &next.Messages[i]
			if msg.RequestID == a.RequestID {
				applyAuthor(msg, a.AuthorConnectionID, a.AuthorDisplayName, a.AuthorRole)
				markMultiplayerForAuthor(&next, a.AuthorConnectionID)
				mergeToolCall(msg, a.Call)
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
	case ActionSetSession:
		next := cloneAppState(st)
		if a.SessionID != "" {
			next.Session.ID = a.SessionID
		}
		if a.Turns != 0 {
			next.Session.Turns = a.Turns
		}
		if a.Checkpoints != nil {
			next.Session.Checkpoints = cloneCheckpoints(a.Checkpoints)
		}
		return next
	case ActionUpdateCost:
		next := cloneAppState(st)
		next.Cost = costStateFromSnapshot(a.Snapshot, a.UpdatedAt)
		return next
	case ActionSetProgress:
		next := cloneAppState(st)
		progress := a.Progress
		next.Progress = &progress
		for i := len(next.Messages) - 1; i >= 0; i-- {
			msg := &next.Messages[i]
			if msg.RequestID == a.Progress.RequestID && msg.Streaming {
				msg.Progress = a.Progress.Message
				applyAuthor(msg, a.AuthorConnectionID, a.AuthorDisplayName, a.AuthorRole)
				markMultiplayerForAuthor(&next, a.AuthorConnectionID)
				break
			}
		}
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
	case ActionSetFileCatalog:
		next := cloneAppState(st)
		next.FileCatalog = cloneFileCatalog(a.Catalog)
		return next
	case ActionSetMultiplayer:
		next := cloneAppState(st)
		next.Multiplayer = cloneMultiplayer(a.Multiplayer)
		return next
	case ActionUpdateMemberTyping:
		next := cloneAppState(st)
		if next.Multiplayer.Typing == nil {
			next.Multiplayer.Typing = map[string]bool{}
		}
		if a.ConnectionID != "" {
			next.Multiplayer.Enabled = true
			if a.Typing {
				next.Multiplayer.Typing[a.ConnectionID] = true
			} else {
				delete(next.Multiplayer.Typing, a.ConnectionID)
			}
			upsertMemberDisplayName(&next.Multiplayer, a.ConnectionID, a.DisplayName)
		}
		if !a.At.IsZero() {
			next.Multiplayer.PresenceAt = a.At
		}
		return next
	case ActionUpdateQueue:
		next := cloneAppState(st)
		next.Multiplayer.Queue = cloneQueueItems(a.Queue)
		positions := map[string]int{}
		for _, item := range a.Queue {
			if item.ConnectionID != "" {
				positions[item.ConnectionID] = item.Position
			}
		}
		for i := range next.Multiplayer.Members {
			next.Multiplayer.Members[i].QueuePosition = positions[next.Multiplayer.Members[i].ConnectionID]
		}
		return next
	case ActionUpdateHunkVotes:
		next := cloneAppState(st)
		key := hunkVoteKey(a.Update)
		if key != "" {
			if next.Multiplayer.HunkVotes == nil {
				next.Multiplayer.HunkVotes = map[string]protocol.HunkVoteUpdate{}
			}
			next.Multiplayer.HunkVotes[key] = cloneHunkVoteUpdate(a.Update)
		}
		return next
	case ActionCancelInFlight:
		next := cloneAppState(st)
		next.InFlight = nil
		return next
	case ActionSetMessageAuthor:
		next := cloneAppState(st)
		for i := len(next.Messages) - 1; i >= 0; i-- {
			msg := &next.Messages[i]
			if msg.RequestID == a.RequestID {
				applyAuthor(msg, a.AuthorConnectionID, a.AuthorDisplayName, a.AuthorRole)
				markMultiplayerForAuthor(&next, a.AuthorConnectionID)
				return next
			}
		}
		return next
	default:
		return cloneAppState(st)
	}
}

func applyAuthor(msg *Message, connectionID, displayName, role string) {
	if connectionID != "" {
		msg.AuthorConnectionID = connectionID
	}
	if displayName != "" {
		msg.AuthorDisplayName = displayName
	}
	if role != "" {
		msg.AuthorRole = role
	}
}

func upsertMemberDisplayName(mp *MultiplayerState, connectionID, displayName string) {
	if displayName == "" {
		return
	}
	for i := range mp.Members {
		if mp.Members[i].ConnectionID == connectionID {
			mp.Members[i].DisplayName = displayName
			return
		}
	}
	mp.Members = append(mp.Members, Member{ConnectionID: connectionID, DisplayName: displayName})
}

func markMultiplayerForAuthor(st *AppState, connectionID string) {
	if connectionID != "" && connectionID != "local" {
		st.Multiplayer.Enabled = true
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
	if st.Progress != nil {
		progress := *st.Progress
		next.Progress = &progress
	}
	next.Provider.Caps = cloneMap(st.Provider.Caps)
	next.Session.Checkpoints = cloneCheckpoints(st.Session.Checkpoints)
	next.FileCatalog = cloneFileCatalog(st.FileCatalog)
	next.Multiplayer = cloneMultiplayer(st.Multiplayer)
	next.Toasts = cloneToasts(st.Toasts)
	return next
}

func mergeToolCall(msg *Message, call ToolCall) {
	idx := toolCallIndex(msg.ToolCalls, call)
	if idx < 0 {
		msg.ToolCalls = append(msg.ToolCalls, cloneToolCalls([]ToolCall{call})[0])
		return
	}
	dst := &msg.ToolCalls[idx]
	if call.EventID != "" {
		dst.EventID = call.EventID
	}
	if call.TurnID != "" {
		dst.TurnID = call.TurnID
	}
	if call.ToolCallID != "" {
		dst.ToolCallID = call.ToolCallID
	}
	if call.ToolName != "" {
		dst.ToolName = call.ToolName
	}
	if call.Status != "" {
		dst.Status = call.Status
	}
	if call.ArgsPreview != "" {
		dst.ArgsPreview = call.ArgsPreview
	}
	if call.ResultPreview != "" {
		dst.ResultPreview = call.ResultPreview
	}
	if call.Error != "" {
		dst.Error = call.Error
	}
	if len(call.Chunks) > 0 {
		dst.Chunks = append(dst.Chunks, call.Chunks...)
	}
}

func toolCallIndex(calls []ToolCall, call ToolCall) int {
	for i := range calls {
		switch {
		case call.ToolCallID != "" && calls[i].ToolCallID == call.ToolCallID:
			return i
		case call.EventID != "" && calls[i].EventID == call.EventID:
			return i
		case call.ToolCallID == "" && call.EventID == "" && call.ToolName != "" && calls[i].ToolName == call.ToolName:
			return i
		}
	}
	return -1
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

func cloneFileCatalog(catalog FileCatalog) FileCatalog {
	if catalog.Files == nil {
		return catalog
	}
	next := catalog
	next.Files = make([]FileCatalogFile, len(catalog.Files))
	copy(next.Files, catalog.Files)
	return next
}

func cloneMultiplayer(mp MultiplayerState) MultiplayerState {
	next := mp
	next.Members = cloneMembers(mp.Members)
	next.Typing = cloneBoolMap(mp.Typing)
	next.Queue = cloneQueueItems(mp.Queue)
	next.HunkVotes = cloneHunkVoteUpdates(mp.HunkVotes)
	return next
}

func cloneMembers(members []Member) []Member {
	if members == nil {
		return nil
	}
	out := make([]Member, len(members))
	copy(out, members)
	return out
}

func cloneQueueItems(items []QueueItem) []QueueItem {
	if items == nil {
		return nil
	}
	out := make([]QueueItem, len(items))
	copy(out, items)
	return out
}

func cloneBoolMap(in map[string]bool) map[string]bool {
	if in == nil {
		return nil
	}
	out := make(map[string]bool, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

func cloneHunkVoteUpdates(in map[string]protocol.HunkVoteUpdate) map[string]protocol.HunkVoteUpdate {
	if in == nil {
		return nil
	}
	out := make(map[string]protocol.HunkVoteUpdate, len(in))
	for key, update := range in {
		out[key] = cloneHunkVoteUpdate(update)
	}
	return out
}

func cloneHunkVoteUpdate(update protocol.HunkVoteUpdate) protocol.HunkVoteUpdate {
	if update.Votes != nil {
		update.Votes = append(protocol.HunkVotes(nil), update.Votes...)
	}
	return update
}

func hunkVoteKey(update protocol.HunkVoteUpdate) string {
	hunkID := update.HunkID
	if hunkID == "" {
		hunkID = update.HunkIDLegacy
	}
	if hunkID == "" {
		return ""
	}
	editID := update.EditID
	if editID == "" {
		editID = update.EditIDLegacy
	}
	return editID + "\x00" + hunkID
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
