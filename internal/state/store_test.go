package state

import (
	"fmt"
	"sync"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
)

func TestAppendChunkDuringStreamingMergesIntoLastMessage(t *testing.T) {
	store := NewStore()
	defer store.Close()
	store.Dispatch(ActionAppendMessage{Msg: Message{ID: "a1", Role: RoleAssistant, RequestID: "r1", Streaming: true}})
	store.Dispatch(ActionAppendChunk{RequestID: "r1", Chunk: "hello", Segments: []MarkdownSegment{{Text: "hello", Plain: "hello", Width: 5}}})
	snapshot := store.Snapshot()
	if got := len(snapshot.Messages); got != 1 {
		t.Fatalf("messages = %d, want 1", got)
	}
	if got := snapshot.Messages[0].Content; got != "hello" {
		t.Fatalf("content = %q, want hello", got)
	}
	if got := len(snapshot.Messages[0].Segments); got != 1 {
		t.Fatalf("segments = %d, want 1", got)
	}
}

func TestAppendMessageCreatesNewMessage(t *testing.T) {
	store := NewStore()
	defer store.Close()
	store.Dispatch(ActionAppendMessage{Msg: Message{ID: "u1", Role: RoleUser, Content: "hi"}})
	snapshot := store.Snapshot()
	if got := len(snapshot.Messages); got != 1 {
		t.Fatalf("messages = %d, want 1", got)
	}
	if got := snapshot.Messages[0].ID; got != "u1" {
		t.Fatalf("message id = %q, want u1", got)
	}
}

func TestCancelInFlightClearsPointer(t *testing.T) {
	store := NewStore()
	defer store.Close()
	store.Dispatch(ActionStartStream{RequestID: "r1", AssistantMsgID: "a1", StartedAt: time.Unix(1, 0)})
	if store.Snapshot().InFlight == nil {
		t.Fatal("inflight = nil, want request")
	}
	store.Dispatch(ActionCancelInFlight{})
	if got := store.Snapshot().InFlight; got != nil {
		t.Fatalf("inflight = %#v, want nil", got)
	}
}

func TestConcurrentDispatchCorrectness(t *testing.T) {
	store := NewStore()
	defer store.Close()
	var wg sync.WaitGroup
	for i := 0; i < MaxMessages; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			store.Dispatch(ActionAppendMessage{Msg: Message{ID: fmt.Sprintf("m-%d", i), Role: RoleUser, Content: "x"}})
		}(i)
	}
	wg.Wait()
	snapshot := store.Snapshot()
	if got := len(snapshot.Messages); got != MaxMessages {
		t.Fatalf("messages = %d, want %d", got, MaxMessages)
	}
	seen := make(map[string]struct{}, MaxMessages)
	for _, msg := range snapshot.Messages {
		seen[msg.ID] = struct{}{}
	}
	if got := len(seen); got != MaxMessages {
		t.Fatalf("unique messages = %d, want %d", got, MaxMessages)
	}
}

func TestSubscriberFanOut(t *testing.T) {
	store := NewStore()
	defer store.Close()
	subA, unsubA := store.Subscribe()
	defer unsubA()
	subB, unsubB := store.Subscribe()
	defer unsubB()
	for i := 0; i < 5; i++ {
		store.Dispatch(ActionAppendMessage{Msg: Message{ID: fmt.Sprintf("m-%d", i), Role: RoleUser}})
	}
	assertSnapshots(t, subA, 5)
	assertSnapshots(t, subB, 5)
}

func TestSnapshotIsolation(t *testing.T) {
	store := NewStore()
	defer store.Close()
	store.Dispatch(ActionAppendMessage{Msg: Message{
		ID:       "m1",
		Role:     RoleUser,
		Content:  "original",
		Segments: []MarkdownSegment{{Text: "original", Plain: "original", Width: 8}},
	}})
	store.Dispatch(ActionSetProvider{Info: protocol.ProviderInfo{
		Name:         "openai",
		Model:        "gpt",
		Capabilities: map[string]any{"streaming": true},
	}})
	snapshot := store.Snapshot()
	snapshot.Messages[0].Content = "mutated"
	snapshot.Messages[0].Segments[0].Text = "mutated"
	snapshot.Provider.Caps["streaming"] = false
	next := store.Snapshot()
	if got := next.Messages[0].Content; got != "original" {
		t.Fatalf("content = %q, want original", got)
	}
	if got := next.Messages[0].Segments[0].Text; got != "original" {
		t.Fatalf("segment text = %q, want original", got)
	}
	if got := next.Provider.Caps["streaming"]; got != true {
		t.Fatalf("provider cap = %v, want true", got)
	}
}

func TestCloseClosesSubscribers(t *testing.T) {
	store := NewStore()
	sub, _ := store.Subscribe()
	store.Close()
	select {
	case _, ok := <-sub:
		if ok {
			t.Fatal("subscriber open after close")
		}
	case <-time.After(time.Second):
		t.Fatal("timed out waiting for subscriber close")
	}
}

func TestMessageWindowing(t *testing.T) {
	store := NewStore()
	defer store.Close()
	for i := 0; i < MaxMessages+1; i++ {
		store.Dispatch(ActionAppendMessage{Msg: Message{ID: fmt.Sprintf("m-%d", i), Role: RoleUser}})
	}
	snapshot := store.Snapshot()
	if got := len(snapshot.Messages); got != MaxMessages {
		t.Fatalf("messages = %d, want %d", got, MaxMessages)
	}
	if got := snapshot.Messages[0].ID; got != "m-1" {
		t.Fatalf("first message = %q, want m-1", got)
	}
}

func assertSnapshots(t *testing.T, ch <-chan AppState, want int) {
	t.Helper()
	for i := 1; i <= want; i++ {
		select {
		case snapshot := <-ch:
			if got := len(snapshot.Messages); got != i {
				t.Fatalf("snapshot messages = %d, want %d", got, i)
			}
		case <-time.After(time.Second):
			t.Fatalf("timed out waiting for snapshot %d", i)
		}
	}
}
