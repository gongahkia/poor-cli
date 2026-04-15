package state

import (
	"context"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

func TestReduceStreamingToolCostAndClonePaths(t *testing.T) {
	now := time.Unix(10, 0)
	st := Reduce(AppState{}, ActionAppendMessage{Msg: Message{ID: "assistant-r1", Role: RoleAssistant, RequestID: "r1", Streaming: true}})
	st = Reduce(st, ActionStartStream{RequestID: "r1", AssistantMsgID: "assistant-r1", StartedAt: now})
	st = Reduce(st, ActionAppendChunk{RequestID: "r1", Chunk: "hello", Segments: []MarkdownSegment{{Text: "hello", Plain: "hello", Width: 5}}})
	st = Reduce(st, ActionAppendThinking{RequestID: "r1", Chunk: "thinking"})
	st = Reduce(st, ActionAppendToolCall{RequestID: "r1", Call: ToolCall{ToolCallID: "call-1", ToolName: "read", Status: "running", Chunks: []string{"a"}}})
	st = Reduce(st, ActionAppendToolCall{RequestID: "r1", Call: ToolCall{ToolCallID: "call-1", Status: "done", ResultPreview: "ok", Chunks: []string{"b"}}})
	if st.InFlight == nil || st.Messages[0].Content != "hello" || st.Messages[0].Thinking != "thinking" {
		t.Fatalf("stream state not updated: %#v", st)
	}
	if got := st.Messages[0].ToolCalls[0]; got.Status != "done" || got.ResultPreview != "ok" || len(got.Chunks) != 2 {
		t.Fatalf("tool merge failed: %#v", got)
	}
	st.Messages[0].ToolCalls[0].Chunks[0] = "mutated"
	cloned := Reduce(st, ActionEndStream{RequestID: "r1", Reason: "done"})
	if cloned.InFlight != nil || cloned.Messages[0].Streaming {
		t.Fatalf("stream not ended: %#v", cloned)
	}
	if cloned.Messages[0].ToolCalls[0].Chunks[0] != "mutated" {
		t.Fatalf("clone lost tool chunk")
	}
}

func TestReduceMetadataActions(t *testing.T) {
	updated := time.Unix(20, 0)
	st := Reduce(AppState{}, ActionSetProvider{Info: protocol.ProviderInfo{Name: "ollama", Model: "llama3.1", Capabilities: map[string]any{"streaming": true}}})
	st = Reduce(st, ActionSetSession{SessionID: "s1", Turns: 3, Checkpoints: []Checkpoint{{ID: "c1"}}})
	st = Reduce(st, ActionUpdateCost{UpdatedAt: updated, Snapshot: protocol.CostSnapshot{
		Session: protocol.CostSession{TotalUSD: 0.02, Turns: 4},
		Summary: protocol.CostSummary{InputTokens: 10, OutputTokens: 5, CacheReadInputTokens: 2},
	}})
	st = Reduce(st, ActionSetProgress{Progress: ProgressState{RequestID: "r1", Phase: "chat", Message: "working"}})
	st = Reduce(st, ActionSetConnection{Phase: Ready})
	st = Reduce(st, ActionToast{Kind: ToastInfo, Text: "ok", TTL: time.Second})
	st = Reduce(st, ActionUpdateContextPressure{Pressure: ContextPressure{Tokens: 8, Budget: 10, Pct: 80}})
	st = Reduce(st, ActionSetFileCatalog{Catalog: FileCatalog{Files: []FileCatalogFile{{Path: "a.go", Language: "go"}}}})
	if st.Provider.Name != "ollama" || st.Session.ID != "s1" || st.Cost.InputTokens != 10 || st.Cost.CacheReadTokens != 2 {
		t.Fatalf("metadata reduce failed: %#v", st)
	}
	if st.Connection.Phase != Ready || len(st.Toasts) != 1 || st.ContextPressure.Tokens != 8 || st.FileCatalog.Files[0].Path != "a.go" {
		t.Fatalf("secondary state failed: %#v", st)
	}
}

func TestStoreRunClosesOnContext(t *testing.T) {
	store := NewStore()
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	if err := store.Run(ctx); err == nil {
		t.Fatal("expected context error")
	}
}
