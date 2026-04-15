package flows

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/gongahkia/gocli-poor/internal/protocol"
	"github.com/gongahkia/gocli-poor/internal/state"
)

type chatCall struct {
	Method string
	Params protocol.ChatStreamingParams
}

type chatNotify struct {
	Method string
	Params any
}

type chatMockRPC struct {
	mu         sync.Mutex
	handlers   map[string][]chatSub
	nextSub    int
	calls      []chatCall
	notifies   []chatNotify
	err        error
	authorID   string
	authorName string
	done       chan struct{}
}

type chatSub struct {
	id int
	h  NotificationHandler
}

func newChatMockRPC(err error) *chatMockRPC {
	return &chatMockRPC{handlers: map[string][]chatSub{}, err: err, done: make(chan struct{})}
}

func (m *chatMockRPC) Call(_ context.Context, method string, params any, _ any) error {
	p := params.(protocol.ChatStreamingParams)
	m.mu.Lock()
	m.calls = append(m.calls, chatCall{Method: method, Params: p})
	m.mu.Unlock()
	m.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: "other", Chunk: "bad"})
	m.emit(protocol.MethodThinkingChunk, protocol.ThinkingChunk{RequestID: p.RequestID, Chunk: "plan"})
	m.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: p.RequestID, Chunk: "Hello ", AuthorConnectionID: m.authorID, AuthorDisplayName: m.authorName})
	if m.err != nil {
		close(m.done)
		return m.err
	}
	m.emit(protocol.MethodToolEvent, protocol.ToolEvent{RequestID: p.RequestID, EventType: "tool_call_start", ToolName: "bash", CallID: "tc1", ToolArgs: map[string]any{"cmd": "pwd"}})
	m.emit(protocol.MethodToolEvent, protocol.ToolEvent{RequestID: p.RequestID, EventType: "tool_result", ToolName: "bash", CallID: "tc1", Message: "ok"})
	m.emit(protocol.MethodCostUpdate, protocol.CostUpdate{RequestID: p.RequestID, InputTokens: 10, OutputTokens: 5, EstimatedCost: 0.01})
	m.emit(protocol.MethodProgress, protocol.Progress{RequestID: p.RequestID, Phase: "write", Message: "writing"})
	m.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: p.RequestID, Chunk: "world", AuthorConnectionID: m.authorID, AuthorDisplayName: m.authorName})
	if m.err == nil {
		m.emit(protocol.MethodStreamChunk, protocol.StreamChunk{RequestID: p.RequestID, Done: true, Reason: "done"})
	}
	close(m.done)
	return m.err
}

func TestChatFlowForwardsStreamAuthorFields(t *testing.T) {
	store := state.NewStore()
	defer store.Close()
	rpc := newChatMockRPC(nil)
	rpc.authorID = "c1"
	rpc.authorName = "alice"
	flow := NewChatFlow(Deps{RPC: rpc, Store: store})

	flow.Start("hello", nil)
	waitChatDone(t, rpc.done)
	if err := flow.Stop(); err != nil {
		t.Fatal(err)
	}

	snap := store.Snapshot()
	if len(snap.Messages) != 2 {
		t.Fatalf("messages=%#v", snap.Messages)
	}
	assistant := snap.Messages[1]
	if assistant.AuthorConnectionID != "c1" || assistant.AuthorDisplayName != "alice" {
		t.Fatalf("author=%q/%q", assistant.AuthorConnectionID, assistant.AuthorDisplayName)
	}
}

func (m *chatMockRPC) Notify(_ context.Context, method string, params any) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.notifies = append(m.notifies, chatNotify{Method: method, Params: params})
	return nil
}

func (m *chatMockRPC) Subscribe(method string, handler NotificationHandler) func() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.nextSub++
	id := m.nextSub
	m.handlers[method] = append(m.handlers[method], chatSub{id: id, h: handler})
	return func() {
		m.mu.Lock()
		defer m.mu.Unlock()
		handlers := m.handlers[method]
		for i, sub := range handlers {
			if sub.id == id {
				m.handlers[method] = append(handlers[:i], handlers[i+1:]...)
				return
			}
		}
	}
}

func (m *chatMockRPC) emit(method string, params any) {
	m.mu.Lock()
	subs := append([]chatSub(nil), m.handlers[method]...)
	m.mu.Unlock()
	for _, sub := range subs {
		sub.h(params)
	}
}

func TestChatFlowStreamsRecordedSession(t *testing.T) {
	store := state.NewStore()
	defer store.Close()
	rpc := newChatMockRPC(nil)
	flow := NewChatFlow(Deps{RPC: rpc, Store: store})

	flow.Start("hello", []string{"main.go"})
	waitChatDone(t, rpc.done)
	if err := flow.Stop(); err != nil {
		t.Fatal(err)
	}

	snap := store.Snapshot()
	if len(snap.Messages) != 2 {
		t.Fatalf("messages=%#v", snap.Messages)
	}
	if snap.Messages[0].Role != state.RoleUser || snap.Messages[0].Content != "hello" {
		t.Fatalf("user message=%#v", snap.Messages[0])
	}
	assistant := snap.Messages[1]
	if assistant.Content != "Hello world" || assistant.Streaming {
		t.Fatalf("assistant=%#v", assistant)
	}
	if assistant.Thinking != "plan" {
		t.Fatalf("thinking=%q", assistant.Thinking)
	}
	if len(assistant.ToolCalls) != 1 || assistant.ToolCalls[0].Status != "ok" || assistant.ToolCalls[0].ResultPreview != "ok" {
		t.Fatalf("tool calls=%#v", assistant.ToolCalls)
	}
	if snap.Progress == nil || snap.Progress.Message != "writing" {
		t.Fatalf("progress=%#v", snap.Progress)
	}
	if snap.InFlight != nil {
		t.Fatalf("inflight=%#v", snap.InFlight)
	}
	rpc.mu.Lock()
	defer rpc.mu.Unlock()
	if len(rpc.calls) != 1 || rpc.calls[0].Method != protocol.MethodChatStreaming {
		t.Fatalf("calls=%#v", rpc.calls)
	}
	if got := rpc.calls[0].Params.ContextFiles; len(got) != 1 || got[0] != "main.go" {
		t.Fatalf("context files=%#v", got)
	}
}

func TestChatFlowRPCErrorFinalizesAndToasts(t *testing.T) {
	store := state.NewStore()
	defer store.Close()
	rpc := newChatMockRPC(errors.New("server crashed"))
	flow := NewChatFlow(Deps{RPC: rpc, Store: store})

	flow.Start("hello", nil)
	waitChatDone(t, rpc.done)
	if err := flow.Stop(); err != nil {
		t.Fatal(err)
	}

	snap := store.Snapshot()
	if snap.InFlight != nil {
		t.Fatalf("inflight=%#v", snap.InFlight)
	}
	if len(snap.Messages) != 2 || snap.Messages[1].Content != "Hello " || snap.Messages[1].Streaming {
		t.Fatalf("messages=%#v", snap.Messages)
	}
	if len(snap.Toasts) == 0 || snap.Toasts[len(snap.Toasts)-1].Kind != state.ToastError {
		t.Fatalf("toasts=%#v", snap.Toasts)
	}
}

func waitChatDone(t *testing.T, done <-chan struct{}) {
	t.Helper()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatalf("chat call timed out")
	}
}
